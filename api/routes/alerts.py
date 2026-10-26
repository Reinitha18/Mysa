from fastapi import APIRouter

from engine.storage import list_alerts

router = APIRouter()


@router.get("")
def get_alerts(limit: int = 100, since_id: int | None = None):
    """Alertes brutes (une par fenêtre signalée), les plus récentes en premier.
    Chaque alerte porte l'identifiant de son épisode ; voir /api/episodes pour la vue regroupée."""
    return list_alerts(limit=limit, since_id=since_id)
