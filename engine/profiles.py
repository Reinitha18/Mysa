"""
Profil de chaque capteur : comment le moteur doit traiter son flux.

  - periodic : le nœud publie à cadence fixe (DHT22, PIR, relais...). Analyse comportementale
               (modèle local / référence) et chien de garde : un silence est anormal.
  - event    : le nœud ne publie que lorsqu'il se passe quelque chose (badge, porte, serrure,
               alarme...). Un silence est NORMAL (personne n'accède) : pas de chien de garde,
               pas de modèle de rythme ; seules les règles s'appliquent. La disparition du
               nœud lui-même est signalée par sa présence (Last Will MQTT, home/<id>/status).
  - state    : configuration ou compteur republié à la connexion (mode du relais, consigne,
               nombre de badges) : enregistré pour le dashboard, jamais analysé.

Un capteur inconnu est traité comme périodique (comportement des versions précédentes,
utilisé par les appareils virtuels).
"""

PERIODIC, EVENT, STATE = "periodic", "event", "state"

SENSOR_KINDS = {
    # esp32-sec-01 : sécurité & accès
    "pir": PERIODIC,
    "door": EVENT,
    "rfid": EVENT,
    "rfid_lockout": EVENT,
    "lock": EVENT,
    "arm": EVENT,
    "alarm": EVENT,
    "badges": STATE,
    # esp32-cmf-01 : confort
    "temperature": PERIODIC,
    "humidity": PERIODIC,
    "relay": PERIODIC,
    "relay_auto": STATE,
    "setpoint": STATE,
    "dht_error": EVENT,
    # caméra (pont du téléphone)
    "motion": EVENT,
}


def sensor_kind(sensor: str) -> str:
    return SENSOR_KINDS.get((sensor or "").strip().lower(), PERIODIC)
