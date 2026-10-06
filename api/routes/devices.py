from fastapi import APIRouter, HTTPException

from engine.storage import list_devices, get_history

router = APIRouter()


@router.get("")
def get_devices():
    """Liste des appareils déjà vus, avec l'horodatage de leur dernier message."""
    return list_devices()


@router.get("/{device_id}/history")
def get_device_history(device_id: str, limit: int = 200):
    history = get_history(device_id, limit=limit)
    if not history:
        raise HTTPException(status_code=404, detail=f"Aucune télémétrie trouvée pour {device_id}")
    return history
