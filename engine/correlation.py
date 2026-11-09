"""
Corrélation entre capteurs : détections qui croisent PLUSIEURS flux pour reconnaître un
scénario de sécurité qu'aucun capteur ne révèle seul (mémoire, chapitre 8).

La couche de règles (engine/rules.py) juge chaque message isolément ; le moteur comportemental
(engine/analyzer.py) compare un flux à son habitude. Ni l'un ni l'autre ne sait, par exemple,
qu'un mouvement n'a de valeur d'alerte que si l'alarme est armée et que personne n'a badgé.
Cette couche comble ce vide avec trois corrélations explicables :

  C-01  mouvement alors que l'alarme est armée et sans badge valide récent   -> intrusion     (high)
  C-02  mouvement confirmé par le PIR ET la caméra dans la même fenêtre       -> présence sûre (high)
  C-03  badge accepté à une heure inhabituelle (apprise, ou plage de nuit)    -> accès suspect (medium)

Hypothèse : un seul foyer (un seul jeu d'appareils). L'état « armé » et les accès sont donc
considérés à l'échelle de la maison, quel que soit le nœud qui les publie.

Couche SANS état propre : tout est relu depuis la base (comme engine/rules.py). Un redémarrage
du moteur ne lui fait rien perdre, et le rejeu hors ligne la teste sans configuration. Chaque
détection enregistre une alerte kind="rule" (source = « corrélation : <nom> »), regroupée en
épisodes comme les autres règles.

Appelée après engine.rules.evaluate (le message courant est alors déjà enregistré en base).
"""

import logging
import os
from datetime import timedelta

from engine.storage import _parse, insert_alert, latest_value, recent_messages

log = logging.getLogger("mysa.correlation")

ARM_SENSORS = {"arm"}                      # value 1 = armé, 0 = désarmé
ACCESS_SENSORS = {"rfid", "lock"}          # value 1 = accès autorisé (badge accepté, serrure ouverte)
PRESENCE_SENSORS = {"pir", "motion"}       # value 1 = présence détectée
PRESENCE_TYPE = {"pir": "PIR", "motion": "caméra"}  # pour le message de corroboration

ACCESS_GRACE_S = 120       # un badge valide dans les 2 min avant un mouvement = entrée légitime
ARM_EXIT_GRACE_S = 60      # délai de sortie : mouvement juste après l'armement, toléré
CORROBORATE_S = 30         # PIR et caméra dans cette fenêtre = présence confirmée
ACCESS_HISTORY_DAYS = 30   # profondeur d'apprentissage des heures d'accès habituelles
MIN_ACCESS_HISTORY = 20    # en-deçà, on n'a pas encore appris : on s'en remet à QUIET_HOURS
UNUSUAL_HOUR_MAX_RATE = 0.05  # une heure vue dans <= 5 % des accès récents est inhabituelle
QUIET_HOURS = set(range(23, 5))  # 23 h à 5 h : heures creuses par défaut (avant apprentissage)

# Les horodatages sont en UTC ; l'heure « locale » sert à juger une heure d'accès.
# Madagascar : UTC+3. Ajustable par la variable d'environnement MYSA_UTC_OFFSET_H.
LOCAL_UTC_OFFSET_H = float(os.getenv("MYSA_UTC_OFFSET_H", "3"))


def _alert(device_id, sensor, ts, name, message, severity):
    info = insert_alert(device_id=device_id, message=message, severity=severity, ts=ts, sensor=sensor,
                        source=f"corrélation : {name}", kind="rule")
    (log.warning if info["new_episode"] else log.debug)(message)
    return {"rule": name, "severity": severity, "message": message}


def _local_hour(ts: str) -> int:
    return int((_parse(ts) + timedelta(hours=LOCAL_UTC_OFFSET_H)).hour)


def _armed_state(meta) -> tuple[bool, str | None]:
    """(armé ?, horodatage du dernier armement). meta['armed'] (publié par la caméra) fait foi
    s'il est présent ; sinon on lit le dernier état du capteur « arm » de la maison."""
    arm = latest_value("arm")
    armed_ts = arm["ts"] if (arm and arm["value"] >= 0.5) else None
    if meta.get("armed") is not None:
        return bool(meta["armed"]), armed_ts
    if arm is None:
        return False, None
    return arm["value"] >= 0.5, armed_ts


def evaluate(device_id: str, sensor: str, value: float, unit: str | None, ts: str,
             meta: dict | None = None) -> list[dict]:
    """Applique les corrélations au message reçu ; retourne les alertes levées."""
    meta = meta or {}
    name = (sensor or "").strip().lower()
    if name in PRESENCE_SENSORS and value >= 0.5:
        return _presence(device_id, name, ts, meta)
    if name in ACCESS_SENSORS and value >= 0.5:
        return _access(device_id, name, ts)
    return []


def _presence(device_id, sensor, ts, meta) -> list[dict]:
    armed, armed_ts = _armed_state(meta)
    if not armed:
        return []
    # Délai de sortie : un mouvement juste après l'armement est normal (l'occupant s'en va).
    if armed_ts and 0 <= (_parse(ts) - _parse(armed_ts)).total_seconds() <= ARM_EXIT_GRACE_S:
        return []
    out = []
    # C-01 : mouvement sans badge valide récent.
    since_access = (_parse(ts) - timedelta(seconds=ACCESS_GRACE_S)).isoformat()
    if not any(r["value"] >= 0.5 for r in recent_messages(ACCESS_SENSORS, since_access)):
        out.append(_alert(device_id, sensor, ts, "mouvement sans accès",
                          f"Mouvement détecté sur {device_id}/{sensor} alors que l'alarme est armée, "
                          f"sans badge valide dans les {ACCESS_GRACE_S} s précédentes (intrusion probable)",
                          "high"))
    # C-02 : présence corroborée par le PIR ET la caméra.
    since_corr = (_parse(ts) - timedelta(seconds=CORROBORATE_S)).isoformat()
    types = {PRESENCE_TYPE.get(r["sensor"]) for r in recent_messages(PRESENCE_SENSORS, since_corr)
             if r["value"] >= 0.5}
    if {"PIR", "caméra"} <= types:
        out.append(_alert(device_id, sensor, ts, "présence confirmée",
                          f"Présence confirmée par le PIR ET la caméra en moins de {CORROBORATE_S} s, "
                          "alarme armée (détection corroborée par deux capteurs indépendants)", "high"))
    return out


def _access(device_id, sensor, ts) -> list[dict]:
    hour = _local_hour(ts)
    since = (_parse(ts) - timedelta(days=ACCESS_HISTORY_DAYS)).isoformat()
    history = [r for r in recent_messages(ACCESS_SENSORS, since)
               if r["value"] >= 0.5 and _parse(r["ts"]) < _parse(ts)]
    learned_unusual, rate = False, None
    if len(history) >= MIN_ACCESS_HISTORY:
        same = sum(1 for r in history if _local_hour(r["ts"]) == hour)
        rate = same / len(history)
        learned_unusual = rate <= UNUSUAL_HOUR_MAX_RATE
    if learned_unusual or hour in QUIET_HOURS:
        why = (f"heure observée dans {rate:.0%} des {len(history)} accès récents"
               if learned_unusual else "plage horaire creuse (avant apprentissage des habitudes)")
        return [_alert(device_id, sensor, ts, "accès à heure inhabituelle",
                       f"Badge accepté sur {device_id}/{sensor} à {hour:02d} h (heure locale) : {why}",
                       "medium")]
    return []
