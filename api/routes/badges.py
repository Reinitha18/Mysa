import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.routes import camera
from engine.storage import get_access, get_history, last_refused_badge, list_access, list_authorized_badges

router = APIRouter()

SEC_NODE = "esp32-sec-01"  # nœud qui porte le lecteur RFID


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


@router.get("/authorized")
def get_authorized():
    """Badges autorisés. Le nœud ne publie que leur nombre (node_count) : la liste vient du registre du
    hub (badges ajoutés ou retirés depuis le dashboard, badges déjà acceptés au lecteur). unknown_count
    = badges présents sur le nœud mais inconnus du hub (ajoutés avant, ou sans passer par lui) : ils
    fonctionnent, mais ne peuvent être retirés qu'en saisissant leur UID."""
    badges = list_authorized_badges()
    last = get_history(SEC_NODE, limit=1, sensor="badges")
    node_count = int(last[0]["value"]) if last else None
    return {"node_count": node_count, "node_ts": last[0]["ts"] if last else None, "known_count": len(badges),
            "unknown_count": None if node_count is None else max(0, node_count - len(badges)), "badges": badges}
