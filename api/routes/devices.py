from fastapi import APIRouter, HTTPException

from engine.risk import device_risks
from engine.storage import get_history, list_devices, list_presence, list_simulated

router = APIRouter()


@router.get("")
def get_devices():
    """Liste des appareils déjà vus, avec l'horodatage de leur dernier message,
    leur score de risque (0 à 100) et le libellé correspondant pour l'occupant."""
    devices = list_devices()
    risks = device_risks()
    presence = list_presence()
    simulated = list_simulated()
    for d in devices:
        p = presence.get(d["device_id"])
        d["online"] = p["online"] if p else None  # None : appareil sans Last Will (virtuel)
        d["presence_ts"] = p["ts"] if p else None
        d["simulated"] = simulated.get(d["device_id"], False)  # mode de repli (le jour J)
        r = risks.get(d["device_id"])
        d["risk"] = r["score"] if r else 0
        d["level"] = r["level"] if r else "normal"
        d["label"] = r["label"] if r else "Tout va bien"
    return devices


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
