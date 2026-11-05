"""
Moteur d'ingestion : s'abonne à tous les topics des appareils (home/#), parse
chaque message de télémétrie et l'enregistre dans la base locale.

Convention de topics et de payload définie au chapitre 7 du mémoire :
  topic   -> home/<device_id>/<sensor>
  payload -> {"device_id": "...", "sensor": "...", "value": ..., "unit": "...", "ts": "..."}

Le TOPIC fait foi : c'est lui que l'ACL du broker contrôle (un compte ne publie que sous
home/<son device_id>/#). Un device_id ou un sensor de la charge utile qui contredit le topic
est rejeté : sinon un nœud compromis pourrait se faire passer pour un autre appareil et
empoisonner sa baseline. Les deux champs sont facultatifs dans la charge utile.

Présence : home/<device_id>/status = "online" | "offline" (texte brut, publié par le nœud à la
connexion, et par le BROKER via le Last Will si le nœud disparaît). Un passage hors ligne lève une
alerte ; c'est elle, et non le silence de chaque capteur, qui signale un nœud événementiel disparu.

Après enregistrement, chaque message passe par les règles (engine/rules.py), puis, pour les flux
périodiques seulement (engine/profiles.py), par l'analyse comportementale.

value doit être numérique : nombre, booléen JSON (converti en 0/1) ou texte numérique.
ts : horodatage de l'appareil accepté si MYSA_TRUST_DEVICE_TS=true (défaut, nécessaire aux
appareils virtuels accélérés) ; sinon, et s'il est absent ou illisible, le moteur horodate le
message à sa réception. Pour les nœuds physiques, false est recommandé (voir watchdog.py).

Lancement : python -m engine.ingest
"""

import json
import logging
import math
import os
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from engine import analyzer, correlation, notify, rules
from engine.profiles import PERIODIC, sensor_kind
from engine.storage import (init_db, insert_access, insert_alert, record_message, set_alert_hook, set_presence,
                            set_simulated)
from engine.watchdog import start_watchdog

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mysa.ingest")

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "true").lower() == "true"
# Certificat de l'autorité (CA) privée qui a signé le certificat du broker.
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT") or None
TRUST_DEVICE_TS = os.getenv("MYSA_TRUST_DEVICE_TS", "true").lower() == "true"

TOPIC_FILTER = "home/#"
META_FIELDS = ("uid", "cause")


class Rejected(ValueError):
    """Message ignoré ; le texte explique pourquoi (journalisé en avertissement)."""


def _number(value) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip().replace(",", "."))
        except ValueError:
            raise Rejected(f"valeur non numérique : {value!r}") from None
    else:
        raise Rejected(f"valeur non numérique : {value!r}")
    if not math.isfinite(number):
        raise Rejected(f"valeur non finie : {value!r}")
    return number


def _timestamp(ts, received_at: str) -> str:
    if not TRUST_DEVICE_TS or not isinstance(ts, str):
        return received_at
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return received_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # sans fuseau : UTC, comme l'horodatage du moteur
    return dt.isoformat()


def parse_message(topic: str, raw: bytes, received_at: str) -> dict | None:
    """Valide un message MQTT. Retourne {device_id, sensor, value, unit, ts, meta}, ou
    {device_id, presence, ts} pour un topic de présence, None pour un topic de commande
    (ignoré sans bruit), ou lève Rejected."""
    parts = topic.split("/")
    if len(parts) >= 3 and parts[2] == "cmd":
        return None  # commandes publiées par l'API, pas de la télémétrie
    if len(parts) == 3 and parts[0] == "home" and parts[1] and parts[2] == "status":
        state = raw.decode("utf-8", "replace").strip().lower()
        if state not in ("online", "offline"):
            raise Rejected(f"présence inconnue : {state[:20]!r}")
        return {"device_id": parts[1], "presence": state, "ts": received_at}
    if len(parts) == 3 and parts[0] == "home" and parts[1] and parts[2] == "sim":
        state = raw.decode("utf-8", "replace").strip().lower()
        return {"device_id": parts[1], "simulated": state in ("1", "true", "on"), "ts": received_at}
    if len(parts) != 3 or parts[0] != "home" or not parts[1] or not parts[2]:
        raise Rejected("topic hors convention home/<device_id>/<sensor>")
    device_id, sensor = parts[1], parts[2]
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise Rejected("message non JSON") from None
    if not isinstance(payload, dict):
        raise Rejected("le JSON n'est pas un objet")
    for field, expected in (("device_id", device_id), ("sensor", sensor)):
        if field in payload and payload[field] != expected:
            raise Rejected(f"{field} {payload[field]!r} contredit le topic ({expected!r}) : usurpation possible")
    if "value" not in payload:
        raise Rejected("champ value absent")
    unit = payload.get("unit")
    # Champs descriptifs facultatifs (UID d'un badge, cause d'une alarme...) : texte court seulement
    meta = {k: payload[k][:64] for k in META_FIELDS if isinstance(payload.get(k), str)}
    if isinstance(payload.get("armed"), bool):
        meta["armed"] = payload["armed"]
    return {"device_id": device_id, "sensor": sensor, "value": _number(payload["value"]),
            "unit": unit if isinstance(unit, str) else None,
            "ts": _timestamp(payload.get("ts"), received_at), "meta": meta}


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        log.info("Connecté au broker MQTT %s:%s", MQTT_HOST, MQTT_PORT)
        client.subscribe(TOPIC_FILTER)
        log.info("Abonné à %s", TOPIC_FILTER)
    else:
        log.error("Échec de connexion au broker (code %s)", reason_code)


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    if reason_code != 0:
        log.warning("Connexion au broker perdue (code %s) : reconnexion automatique", reason_code)


def on_message(client, userdata, msg):
    received_at = datetime.now(timezone.utc).isoformat()  # horodatage dès la réception du message
    try:
        m = parse_message(msg.topic, msg.payload, received_at)
    except Rejected as err:
        log.warning("Message ignoré sur %s : %s", msg.topic, err)
        return
    if m is None:
        return
    if "presence" in m:
        handle_presence(m["device_id"], m["presence"] == "online", m["ts"])
        return
    if "simulated" in m:
        set_simulated(m["device_id"], m["simulated"], m["ts"])
        log.info("Appareil %s : mode %s", m["device_id"], "simulation" if m["simulated"] else "réel")
        return
    handle_telemetry(m)


def handle_presence(device_id: str, online: bool, ts: str):
    previous = set_presence(device_id, online, ts)
    if online:
        analyzer.note_reconnect(device_id, ts)
        log.info("Nœud %s en ligne", device_id)
    elif previous is not False:  # pas de doublon si l'état « hors ligne » est republié
        message = f"Le nœud {device_id} est hors ligne (déconnexion détectée par le broker)"
        insert_alert(device_id=device_id, message=message, severity="high", ts=ts, sensor="status",
                     source="présence", kind="offline")
        log.warning(message)


def handle_telemetry(m: dict):
    ts = record_message(m["device_id"], m["sensor"], m["value"], m["unit"], m["ts"])
    log.info("Télémétrie enregistrée : %s/%s = %s", m["device_id"], m["sensor"], m["value"])
    if m["sensor"] == "rfid":  # journal des accès : l'API y joint la photo de la caméra
        insert_access(m["device_id"], (m.get("meta") or {}).get("uid"), m["value"] >= 0.5, ts)

    try:  # une erreur d'analyse ne doit pas arrêter la réception des messages
        rules.evaluate(m["device_id"], m["sensor"], m["value"], m["unit"], ts, m.get("meta"))
        correlation.evaluate(m["device_id"], m["sensor"], m["value"], m["unit"], ts, m.get("meta"))
        if sensor_kind(m["sensor"]) == PERIODIC:
            analyzer.evaluate(m["device_id"], m["sensor"], ts, m["unit"])
    except Exception:
        log.exception("Erreur d'analyse sur %s/%s", m["device_id"], m["sensor"])


def build_client() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mysa-engine")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    if MQTT_USE_TLS:
        client.tls_set(ca_certs=MQTT_CA_CERT)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    return client


def main():
    init_db()
    set_alert_hook(notify.on_alert)  # notifications (e-mail / SMS) sur les alertes marquantes
    start_watchdog()
    client = build_client()
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever(retry_first_connection=True)  # broker absent au démarrage : on réessaie


if __name__ == "__main__":
    main()
