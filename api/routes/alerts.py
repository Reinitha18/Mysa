from fastapi import APIRouter

from engine.storage import list_alerts

router = APIRouter()


@router.get("")
def get_alerts(limit: int = 100):
    """Dernières alertes générées par le moteur, les plus récentes en premier."""
    return list_alerts(limit=limit)
