"""
Extraction de caractéristiques comportementales par appareil, à partir de son
historique de télémétrie récent. Ce sont ces caractéristiques — pas la valeur
brute d'un capteur — que le modèle (model.py) compare à la baseline apprise.

Version actuelle : un premier jeu de caractéristiques simples, volontairement
limité, à enrichir au fil de l'implémentation (par exemple : régularité des
intervalles, écart-type des valeurs par capteur, répartition horaire).
"""

from datetime import datetime, timezone

import pandas as pd

from engine.storage import get_history


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def extract_features(device_id: str, window_size: int = 50) -> dict:
    """Calcule un petit vecteur de caractéristiques sur les `window_size`
    derniers messages de l'appareil. Retourne un dict vide si l'historique
    est insuffisant pour être significatif."""
    rows = get_history(device_id, limit=window_size)
    if len(rows) < 5:
        return {}

    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].apply(_parse_ts)
    df = df.sort_values("ts")

    intervals = df["ts"].diff().dt.total_seconds().dropna()
    now = datetime.now(timezone.utc)
    last_seen_s = (now - df["ts"].iloc[-1]).total_seconds()

    return {
        "message_count": len(df),
        "mean_interval_s": float(intervals.mean()) if not intervals.empty else 0.0,
        "std_interval_s": float(intervals.std()) if len(intervals) > 1 else 0.0,
        "mean_value": float(pd.to_numeric(df["value"], errors="coerce").mean()),
        "distinct_sensors": int(df["sensor"].nunique()),
        "seconds_since_last_message": last_seen_s,
    }
