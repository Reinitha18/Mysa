from fastapi import APIRouter

from engine.storage import list_episodes

router = APIRouter()


@router.get("")
def get_episodes(limit: int = 100, device_id: str | None = None):
    """Épisodes d'alerte : les alertes d'un même flux rapprochées dans le temps sont regroupées
    (début, fin, nombre d'alertes, score minimal). C'est la vue à privilégier pour l'utilisateur."""
    return list_episodes(limit=limit, device_id=device_id)
