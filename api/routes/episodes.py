from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.storage import list_episodes, set_episode_ack

router = APIRouter()


class Ack(BaseModel):
    acknowledged: bool = True
    note: str | None = None


class AckMany(Ack):
    ids: list[int] = Field(min_length=1, max_length=500)


@router.get("")
def get_episodes(limit: int = 100, device_id: str | None = None):
    """Épisodes d'alerte : les alertes d'un même flux rapprochées dans le temps sont regroupées
    (début, fin, nombre d'alertes, score minimal, acquittement). Vue à privilégier pour l'utilisateur."""
    return list_episodes(limit=limit, device_id=device_id)


@router.post("/{episode_id}/ack")
def ack_episode(episode_id: int, ack: Ack = Ack()):
    """Acquitte un épisode depuis le dashboard (ou le dé-acquitte avec acknowledged=false).
    L'acquittement marque l'épisode comme pris en compte ; il ne change pas le score de risque."""
    episode = set_episode_ack(episode_id, acknowledged=ack.acknowledged, note=ack.note)
    if episode is None:
        raise HTTPException(status_code=404, detail=f"Épisode inconnu : {episode_id}")
    return episode


@router.post("/ack")
def ack_episodes(body: AckMany):
    """Acquitte (ou rouvre) plusieurs épisodes d'un coup, depuis la sélection du dashboard. Les épisodes
    inconnus sont signalés dans « missing » sans bloquer les autres."""
    missing = [i for i in dict.fromkeys(body.ids)
               if set_episode_ack(i, acknowledged=body.acknowledged, note=body.note) is None]
    return {"updated": len(set(body.ids)) - len(missing), "missing": missing}
