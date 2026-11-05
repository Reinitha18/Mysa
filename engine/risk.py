"""
Score de risque par appareil (mémoire, section 8.5.5) : un nombre de 0 à 100, lisible par
un non-spécialiste, qui résume les épisodes d'alerte récents de l'appareil.

  - Ce sont les ÉPISODES qui comptent, pas les alertes brutes : les fenêtres glissantes
    multiplient les alertes d'une même déviation (5.6), ce qui gonflerait le score.
  - Chaque épisode contribue selon sa gravité (WEIGHTS), et sa contribution décroît avec
    l'âge de sa dernière alerte (constante TAU_S) : un appareil redevenu normal voit son
    score revenir vers zéro.
  - Un avis de la garde de compatibilité (référence abandonnée) pèse comme une gravité
    « low » : il accompagne souvent l'installation d'un appareil.
  - Un flux ACTUELLEMENT silencieux ajoute SILENT_WEIGHT sans décroissance, tant qu'il le reste ;
    un nœud ACTUELLEMENT hors ligne (Last Will) ajoute OFFLINE_WEIGHT de la même façon.

Niveaux affichés : normal (0 à 24), à surveiller (25 à 59), critique (60 à 100).
Poids, constante de décroissance et seuils sont des choix initiaux, à calibrer (chapitre 9).
"""

import math
from datetime import datetime, timedelta, timezone

from engine.storage import _parse, list_episodes_since, list_presence, list_streams

WEIGHTS = {"low": 10, "medium": 20, "high": 40}
NOTICE_WEIGHT = WEIGHTS["low"]
SILENT_WEIGHT = 30
OFFLINE_WEIGHT = 40
TAU_S = 30 * 60
HORIZON_S = 6 * TAU_S  # au-delà, la contribution est inférieure à 0,25 % : ignorée

LEVELS = [(60, "critique", "Alerte"), (25, "à surveiller", "À surveiller"), (0, "normal", "Tout va bien")]


def risk_score(episodes) -> int:
    """episodes : liste de (gravité, âge en secondes) ; retourne un entier de 0 à 100."""
    total = sum(WEIGHTS.get(sev, WEIGHTS["low"]) * math.exp(-max(age, 0.0) / TAU_S) for sev, age in episodes)
    return min(100, round(total))


def level(score: int) -> tuple[str, str]:
    """(niveau, libellé pour l'occupant)"""
    for floor, name, label in LEVELS:
        if score >= floor:
            return name, label
    return LEVELS[-1][1], LEVELS[-1][2]


def device_risks(now: datetime | None = None, device_id: str | None = None) -> dict[str, dict]:
    """Score de risque de chaque appareil (ou d'un seul), avec ses principales causes."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(seconds=HORIZON_S)).isoformat()
    per_device: dict[str, list] = {}
    for e in list_episodes_since(since, device_id=device_id):
        age = (now - _parse(e["end_ts"])).total_seconds()
        sev = "low" if e["kind"] == "notice" else e["severity"]
        weight = WEIGHTS.get(sev, NOTICE_WEIGHT) * math.exp(-max(age, 0.0) / TAU_S)
        per_device.setdefault(e["device_id"], []).append(
            {"episode_id": e["id"], "sensor": e["sensor"], "kind": e["kind"], "severity": sev,
             "source": e["source"], "start_ts": e["start_ts"], "end_ts": e["end_ts"],
             "alert_count": e["alert_count"], "contribution": round(weight, 1), "_sev_age": (sev, age)})
    silent = {}
    for s in list_streams():
        if s["silent"] and (device_id is None or s["device_id"] == device_id):
            silent.setdefault(s["device_id"], []).append(s["sensor"])

    offline = {d for d, p in list_presence().items() if not p["online"] and (device_id is None or d == device_id)}

    out = {}
    for dev in sorted(set(per_device) | set(silent) | offline | ({device_id} if device_id else set())):
        eps = per_device.get(dev, [])
        score = risk_score([e.pop("_sev_age") for e in eps])
        score = min(100, score + SILENT_WEIGHT * len(silent.get(dev, [])) + OFFLINE_WEIGHT * (dev in offline))
        name, label = level(score)
        eps.sort(key=lambda e: -e["contribution"])
        out[dev] = {"device_id": dev, "score": score, "level": name, "label": label,
                    "silent_sensors": silent.get(dev, []), "offline": dev in offline, "causes": eps[:5]}
    return out
