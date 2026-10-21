"""
Moteur d'ingestion : s'abonne à tous les topics des appareils (home/#), parse
chaque message de télémétrie et l'enregistre dans la base locale.

Convention de topics et de payload définie au chapitre 7 du mémoire :
  topic   -> home/<device_id>/<sensor>
  payload -> {"device_id": "...", "sensor": "...", "value": ..., "unit": "...", "ts": "..."}

Lancement : python -m engine.ingest
"""

import json
import logging
import os

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from engine import analyzer
from engine.storage import init_db, insert_telemetry, touch_stream
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

TOPIC_FILTER = "home/#"


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        log.info("Connecté au broker MQTT %s:%s", MQTT_HOST, MQTT_PORT)
        client.subscribe(TOPIC_FILTER)
        log.info("Abonné à %s", TOPIC_FILTER)
    else:
        log.error("Échec de connexion au broker (code %s)", reason_code)


def on_message(client, userdata, msg):
    # Les commandes (home/<device>/cmd/<actionneur>) ne sont pas de la
    # télémétrie entrante : on les ignore ici, elles sont publiées par
    # l'API, pas consommées par le moteur.
    if "/cmd/" in msg.topic:
        return

    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        log.warning("Message non JSON ignoré sur %s", msg.topic)
        return

    if not isinstance(payload, dict):
        log.warning("Message ignoré sur %s : le JSON n'est pas un objet", msg.topic)
        return

    device_id = payload.get("device_id")
    sensor = payload.get("sensor")
    value = payload.get("value")
    unit = payload.get("unit")
    ts = payload.get("ts")

    if not device_id or not sensor:
        log.warning("Message incomplet ignoré sur %s : %s", msg.topic, payload)
        return

    ts = insert_telemetry(device_id=device_id, sensor=sensor, value=value, unit=unit, ts=ts)
    log.info("Télémétrie enregistrée : %s/%s = %s", device_id, sensor, value)

    try:
        touch_stream(device_id, sensor, ts)
        analyzer.evaluate(device_id, sensor, ts)
    except Exception:  # une erreur d'analyse ne doit pas arrêter la réception des messages
        log.exception("Erreur d'analyse sur %s/%s", device_id, sensor)


def build_client() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mysa-engine")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    if MQTT_USE_TLS:
        client.tls_set(ca_certs=MQTT_CA_CERT)
    client.on_connect = on_connect
    client.on_message = on_message
    return client


def main():
    init_db()
    start_watchdog()
    client = build_client()
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
