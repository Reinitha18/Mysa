import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.routes import camera
from engine.storage import get_access, last_refused_badge, list_access

router = APIRouter()


@router.get("/last-refused")
def get_last_refused():
    """UID du dernier badge refusé, pour l'enrôler en un clic depuis le dashboard
    (commande badge_add). {"uid", "device_id", "ts"} ou null si aucun refus connu."""
    return last_refused_badge()


@router.get("/access")
def get_access_log(limit: int = 30):
    """Journal des accès, du plus récent au plus ancien : badge, accepté ou refusé, et photo prise
    par la caméra à cet instant (has_capture ; null tant que l'API ne l'a pas encore traitée)."""
    rows = list_access(min(max(limit, 1), 200))
    for r in rows:
        r["granted"] = bool(r["granted"])
        r["has_capture"] = None if r["capture"] is None else bool(r["capture"])
        del r["capture"]
    return rows


@router.get("/access/{access_id}/capture")
def get_access_capture(access_id: int):
    """Photo JPEG d'un accès (protégée par le mot de passe du dashboard comme toute l'API)."""
    access = get_access(access_id)
    path = os.path.join(camera.CAPTURE_DIR, access["capture"]) if access and access["capture"] else None
    if not path or not os.path.isfile(path):
        raise HTTPException(404, "Aucune photo pour cet accès")
    return FileResponse(path, media_type="image/jpeg")
