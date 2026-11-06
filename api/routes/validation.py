"""
Journal des campagnes de validation : scénarios d'intrusion TI-01 à TI-05 du lab d'attaque
(attack-lab/run_report.py), exécutés depuis la VM Kali.

Le script de rapport envoie ici le résultat de chaque campagne (POST) ; le dashboard les relit (GET) et
y associe les épisodes d'alerte levés par Mysa pendant la campagne. Comme toute l'API, ces routes exigent
la session du dashboard quand MYSA_DASHBOARD_PASSWORD est défini (le script de Kali s'y connecte).
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.storage import insert_attack_run, list_attack_runs, list_episodes_since

router = APIRouter()

STATUSES = ("blocked", "detected", "undetected", "not_run")
EPISODE_GRACE_S = 60   # une alerte peut tomber un peu après la fin du dernier scénario
EPISODE_LIMIT = 30


class AttackResult(BaseModel):
    ti: str = Field(max_length=16)
    name: str = Field(max_length=120)
    before: str | None = Field(None, max_length=400)
    status: str = Field(max_length=16)
    delay_s: float | None = Field(None, ge=0, le=3600)
    note: str | None = Field(None, max_length=800)


class AttackRun(BaseModel):
    started_ts: str
    finished_ts: str
    target: str | None = Field(None, max_length=120)
    results: list[AttackResult] = Field(min_length=1, max_length=20)


def _parse(ts: str) -> datetime:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, f"Horodatage invalide : {ts}") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.post("/runs", status_code=201)
def post_run(run: AttackRun):
    """Enregistre une campagne et ses résultats (status : blocked, detected, undetected, not_run)."""
    start, end = _parse(run.started_ts), _parse(run.finished_ts)
    if end < start:
        raise HTTPException(422, "finished_ts antérieur à started_ts")
    bad = [r.ti for r in run.results if r.status not in STATUSES]
    if bad:
        raise HTTPException(422, f"Statut inconnu pour {', '.join(bad)} (attendu : {', '.join(STATUSES)})")
    run_id = insert_attack_run(start.isoformat(), end.isoformat(), run.target, [r.model_dump() for r in run.results])
    return {"id": run_id}


@router.get("/runs")
def get_runs(limit: int = 10):
    """Dernières campagnes (la plus récente d'abord), avec leur résumé et les épisodes d'alerte de Mysa
    survenus pendant la campagne : ce que le moteur a vu pendant que les attaques se déroulaient."""
    runs = list_attack_runs(min(max(limit, 1), 50))
    for run in runs:
        counts = {s: 0 for s in STATUSES}
        for r in run["results"]:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        run["summary"] = counts
        start, end = _parse(run["started_ts"]), _parse(run["finished_ts"]) + timedelta(seconds=EPISODE_GRACE_S)
        run["episodes"] = [e for e in list_episodes_since(run["started_ts"])
                           if _parse(e["start_ts"]) <= end][:EPISODE_LIMIT]
    return runs
