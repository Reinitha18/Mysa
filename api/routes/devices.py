import glob
import os
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.risk import device_risks
from engine.storage import (default_house_id, delete_device, delete_sensor, device_known, get_history, get_house,
                            list_device_meta, list_devices, list_presence, list_sensor_meta, list_simulated,
                            list_streams, upsert_device_meta, upsert_sensor_meta)

router = APIRouter()

DEVICE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,39}")
SENSOR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")


class DeviceIn(BaseModel):
    device_id: str
    name: str = Field(max_length=60)
    kind: str | None = Field(None, max_length=60)
    house_id: int | None = None


class DevicePatch(BaseModel):
    name: str | None = Field(None, max_length=60)
    kind: str | None = Field(None, max_length=60)
    house_id: int | None = None


class SensorIn(BaseModel):
    sensor: str
    label: str | None = Field(None, max_length=60)
    unit: str | None = Field(None, max_length=16)


class SensorPatch(BaseModel):
    label: str | None = Field(None, max_length=60)
    unit: str | None = Field(None, max_length=16)


def _text(value: str | None, field: str, required: bool = False) -> str | None:
    value = (value or "").strip() or None
    if required and value is None:
        raise HTTPException(422, f"{field} obligatoire")
    return value


def _check_house(house_id: int | None):
    if house_id is not None and get_house(house_id) is None:
        raise HTTPException(422, f"Maison inconnue : {house_id}")


def _forget_models(device_id: str, sensor: str | None = None):
    """Efface les modèles de référence appris (engine/models/<appareil>__<capteur>.joblib) : un appareil
    recréé plus tard ne doit pas hériter de l'ancien comportement."""
    from engine import model  # import tardif : le moteur ne doit pas alourdir le démarrage de l'API
    pattern = f"{glob.escape(device_id)}__{glob.escape(sensor) if sensor else '*'}"
    for path in glob.glob(os.path.join(glob.escape(model.MODELS_DIR), pattern + ".*")):
        os.remove(path)
    model._cache.clear()


@router.get("")
def get_devices():
    """Liste des appareils (vus par le moteur, ou déclarés depuis le dashboard et pas encore entendus), avec
    l'horodatage de leur dernier message, leur score de risque (0 à 100), le libellé pour l'occupant, et leur
    fiche (nom, type, maison)."""
    devices = list_devices()
    meta = list_device_meta()
    seen = {d["device_id"] for d in devices}
    devices += [{"device_id": did, "last_seen": None, "message_count": 0} for did in meta if did not in seen]
    risks, presence, simulated, home = device_risks(), list_presence(), list_simulated(), default_house_id()
    for d in devices:
        m = meta.get(d["device_id"])
        d["name"], d["kind"] = (m["name"], m["kind"]) if m else (None, None)
        d["house_id"] = (m["house_id"] if m else None) or home
        d["registered"] = m is not None
        d["waiting"] = d["last_seen"] is None  # déclaré, aucun message reçu pour l'instant
        p = presence.get(d["device_id"])
        d["online"] = p["online"] if p else None  # None : appareil sans Last Will (virtuel)
        d["presence_ts"] = p["ts"] if p else None
        d["simulated"] = simulated.get(d["device_id"], False)  # mode de repli (le jour J)
        r = risks.get(d["device_id"])
        d["risk"] = r["score"] if r else 0
        d["level"] = r["level"] if r else "normal"
        d["label"] = "En attente" if d["waiting"] else (r["label"] if r else "Tout va bien")
    return devices


@router.post("", status_code=201)
def create_device(body: DeviceIn):
    """Déclare un appareil avant son premier message. Son identifiant doit être celui de ses topics MQTT
    (home/<identifiant>/...), sinon il ne sera jamais associé aux mesures."""
    device_id = body.device_id.strip()
    if not DEVICE_ID_RE.fullmatch(device_id):
        raise HTTPException(422, "Identifiant invalide : 2 à 40 caractères (lettres, chiffres, - et _)")
    if device_known(device_id):
        raise HTTPException(409, f"L'appareil {device_id} existe déjà")
    _check_house(body.house_id)
    fields = {"name": _text(body.name, "Nom", required=True), "kind": _text(body.kind, "Type"), "house_id": body.house_id}
    upsert_device_meta(device_id, fields)
    return {"device_id": device_id, **fields}


@router.get("/sensor-meta")
def get_sensor_meta():
    """Libellés et unités saisis pour les capteurs : {appareil: {capteur: {label, unit}}}."""
    return list_sensor_meta()


@router.put("/{device_id}")
def update_device(device_id: str, body: DevicePatch):
    """Renomme un appareil, change son type ou sa maison (null = valeur par défaut)."""
    if not device_known(device_id):
        raise HTTPException(404, f"Appareil inconnu : {device_id}")
    changes = body.model_dump(exclude_unset=True)
    if "house_id" in changes:
        _check_house(changes["house_id"])
    for key in ("name", "kind"):
        if key in changes:
            changes[key] = _text(changes[key], key)
    upsert_device_meta(device_id, changes)
    return {"device_id": device_id, **list_device_meta()[device_id]}


@router.delete("/{device_id}")
def remove_device(device_id: str):
    """Supprime l'appareil et tout son historique (mesures, alertes, épisodes, modèles appris). S'il publie
    encore, le moteur le re-découvrira comme un nouvel appareil."""
    if not device_known(device_id):
        raise HTTPException(404, f"Appareil inconnu : {device_id}")
    n = delete_device(device_id)
    _forget_models(device_id)
    return {"deleted": device_id, "measurements": n}


@router.get("/{device_id}/history")
def get_device_history(device_id: str, limit: int = 200, sensor: str | None = None):
    history = get_history(device_id, limit=limit, sensor=sensor)
    if not history:
        raise HTTPException(status_code=404, detail=f"Aucune télémétrie trouvée pour {device_id}")
    return history


@router.get("/{device_id}/risk")
def get_device_risk(device_id: str):
    """Score de risque de l'appareil (0 à 100), niveau (normal, à surveiller, critique) et
    principaux épisodes qui l'expliquent (mémoire, section 8.5.5)."""
    if not get_history(device_id, limit=1):
        raise HTTPException(status_code=404, detail=f"Appareil inconnu : {device_id}")
    return device_risks(device_id=device_id)[device_id]


# ---------- Capteurs d'un appareil ----------
def _sensors_of(device_id: str) -> tuple[dict, dict]:
    streams = {s["sensor"]: s for s in list_streams() if s["device_id"] == device_id}
    return streams, list_sensor_meta().get(device_id, {})


@router.get("/{device_id}/sensors")
def get_sensors(device_id: str):
    """Capteurs de l'appareil : ceux qui ont publié (découverts par le moteur) et ceux déclarés depuis le dashboard."""
    if not device_known(device_id):
        raise HTTPException(404, f"Appareil inconnu : {device_id}")
    streams, meta = _sensors_of(device_id)
    rows = []
    for sensor in sorted(set(streams) | set(meta)):
        s, m = streams.get(sensor), meta.get(sensor, {})
        rows.append({"sensor": sensor, "label": m.get("label"), "unit": m.get("unit"), "discovered": s is not None,
                     "message_count": s["message_count"] if s else 0, "silent": bool(s and s["silent"]),
                     "last_ts": s["last_ts"] if s else None})
    return rows


@router.post("/{device_id}/sensors", status_code=201)
def create_sensor(device_id: str, body: SensorIn):
    """Déclare un capteur (nom d'affichage, unité) avant sa première mesure. La clé doit être celle de
    ses topics MQTT (home/<appareil>/<capteur>)."""
    if not device_known(device_id):
        raise HTTPException(404, f"Appareil inconnu : {device_id}")
    sensor = body.sensor.strip()
    if not SENSOR_RE.fullmatch(sensor):
        raise HTTPException(422, "Clé de capteur invalide : 1 à 40 caractères (lettres, chiffres, - et _)")
    streams, meta = _sensors_of(device_id)
    if sensor in streams or sensor in meta:
        raise HTTPException(409, f"Le capteur {sensor} existe déjà sur cet appareil")
    fields = {"label": _text(body.label, "Nom"), "unit": _text(body.unit, "Unité")}
    upsert_sensor_meta(device_id, sensor, fields)
    return {"device_id": device_id, "sensor": sensor, **fields}


@router.put("/{device_id}/sensors/{sensor}")
def update_sensor(device_id: str, sensor: str, body: SensorPatch):
    """Change le nom d'affichage ou l'unité d'un capteur (null = valeur par défaut)."""
    streams, meta = _sensors_of(device_id)
    if sensor not in streams and sensor not in meta:
        raise HTTPException(404, f"Capteur inconnu : {device_id}/{sensor}")
    changes = {k: _text(v, k) for k, v in body.model_dump(exclude_unset=True).items()}
    upsert_sensor_meta(device_id, sensor, changes)
    return {"device_id": device_id, "sensor": sensor, **list_sensor_meta().get(device_id, {}).get(sensor, {})}


@router.delete("/{device_id}/sensors/{sensor}")
def remove_sensor(device_id: str, sensor: str):
    """Supprime le capteur avec ses mesures, alertes, épisodes et son modèle appris. S'il publie encore,
    le moteur le re-découvrira."""
    streams, meta = _sensors_of(device_id)
    if sensor not in streams and sensor not in meta:
        raise HTTPException(404, f"Capteur inconnu : {device_id}/{sensor}")
    n = delete_sensor(device_id, sensor)
    _forget_models(device_id, sensor)
    return {"deleted": sensor, "measurements": n}
