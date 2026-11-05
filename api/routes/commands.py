"""
Commandes des actionneurs : l'API publie sur home/<device_id>/cmd/<actionneur> avec le compte du
moteur (mysa-engine), seul autorisé à écrire sur home/+/cmd/# par l'ACL du broker.

Seuls les actionneurs et valeurs de ACTUATORS sont acceptés (ceux du firmware des nœuds) : l'API
ne sert pas de relais MQTT générique. Les commandes exigent la session du dashboard quand
MYSA_DASHBOARD_PASSWORD est défini (api/auth.py). MYSA_ENABLE_COMMANDS=0 désactive les commandes.
"""

import os
import re

import paho.mqtt.publish as publish
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

UID_PATTERN = r"^[0-9A-Fa-f]{2}( [0-9A-Fa-f]{2}){3,9}$"  # UID RFID : "29 2F 3A 03"

ACTUATORS = {
    "esp32-sec-01": {
        "lock": {"label": "Serrure", "values": ["open", "close"]},
        "arm": {"label": "Alarme", "values": ["on", "off"]},
        "alarm": {"label": "Sirène d'alarme (arrêt)", "values": ["off"]},
        "buzzer": {"label": "Buzzer (test)", "values": ["on", "off"]},
        "led": {"label": "Voyant", "values": ["on", "off"]},
        "badge_add": {"label": "Autoriser un badge", "pattern": UID_PATTERN},
        "badge_del": {"label": "Retirer un badge", "pattern": UID_PATTERN},
    },
    "esp32-cmf-01": {
        "relay": {"label": "Lampe / prise", "values": ["on", "off"]},
        "mode": {"label": "Mode du relais", "values": ["manual", "auto"]},
        "setpoint": {"label": "Consigne du thermostat (°C)", "range": [10, 40]},
    },
}


class Command(BaseModel):
    device_id: str
    actuator: str
    value: str


def _publish(topic: str, payload: str):
    tls = None
    if os.getenv("MQTT_USE_TLS", "true").lower() == "true":
        tls = {"ca_certs": os.getenv("MQTT_CA_CERT") or None}
    auth = None
    if os.getenv("MQTT_USER"):
        auth = {"username": os.getenv("MQTT_USER"), "password": os.getenv("MQTT_PASSWORD")}
    publish.single(topic, payload, qos=1, hostname=os.getenv("MQTT_HOST", "localhost"),
                   port=int(os.getenv("MQTT_PORT", "8883")), client_id="mysa-api", auth=auth, tls=tls)


def _valid(spec: dict, value: str) -> bool:
    if "values" in spec:
        return value in spec["values"]
    if "pattern" in spec:
        return re.fullmatch(spec["pattern"], value) is not None
    try:
        return spec["range"][0] <= float(value) <= spec["range"][1]
    except ValueError:
        return False


@router.get("")
def get_actuators():
    """Actionneurs commandables, par appareil, avec leurs valeurs possibles."""
    return {"enabled": os.getenv("MYSA_ENABLE_COMMANDS", "1") == "1", "actuators": ACTUATORS}


@router.post("")
def send_command(cmd: Command):
    """Publie une commande vers un actionneur connu."""
    if os.getenv("MYSA_ENABLE_COMMANDS", "1") != "1":
        raise HTTPException(status_code=403, detail="Commandes désactivées (MYSA_ENABLE_COMMANDS=0)")
    spec = ACTUATORS.get(cmd.device_id, {}).get(cmd.actuator)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Actionneur inconnu : {cmd.device_id}/{cmd.actuator}")
    if not _valid(spec, cmd.value):
        raise HTTPException(status_code=422, detail=f"Valeur refusée pour {cmd.actuator} : {cmd.value}")
    topic = f"home/{cmd.device_id}/cmd/{cmd.actuator}"
    try:
        _publish(topic, cmd.value)
    except (OSError, ValueError) as err:
        raise HTTPException(status_code=502, detail=f"Broker MQTT injoignable : {err}") from None
    return {"topic": topic, "value": cmd.value, "sent": True}
