"""
Extraction de caractéristiques comportementales par flux capteur
(un flux = un appareil + un de ses capteurs).

Pourquoi par capteur et non par appareil : un même ESP32 publie des grandeurs
d'unités différentes (ex. DHT22 + RFID). Les mélanger dans une même moyenne
n'a pas de sens, et empêcherait d'associer un flux à une catégorie.

Deux jeux de caractéristiques, calculés par la MÊME fonction pure
(`window_features`) pour les données publiques et pour la télémétrie réelle :
  - PORTABLE_FEATURES : dynamique des valeurs uniquement (variation, dispersion,
    diversité). Le rythme de publication est exclu : il dépend du firmware et
    du processus d'échantillonnage du dataset, pas de la catégorie ->
    modèles de référence ;
  - LOCAL_FEATURES : ajoutent régularité et rythme de publication, niveau moyen
    -> modèle local, appris sur la télémétrie réelle de l'appareil.

Fenêtre FIXE de WINDOW messages : une fenêtre qui grossit pendant
l'apprentissage fausserait la baseline.
"""

from datetime import datetime

import numpy as np

from engine.storage import get_history

WINDOW = 20

PORTABLE_FEATURES = ["mean_abs_delta", "std_value", "unique_ratio"]
LOCAL_FEATURES = PORTABLE_FEATURES + ["cv_interval", "mean_value", "mean_interval_s", "std_interval_s"]


def _parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def window_features(ts: np.ndarray, values: np.ndarray) -> dict:
    """Caractéristiques d'une fenêtre chronologique (ts en secondes epoch)."""
    ts = np.asarray(ts, dtype=float)
    values = np.asarray(values, dtype=float)
    intervals = np.diff(ts)
    mean_i = float(intervals.mean()) if len(intervals) else 0.0
    std_i = float(intervals.std(ddof=1)) if len(intervals) > 1 else 0.0
    return {
        "cv_interval": std_i / mean_i if mean_i > 0 else 0.0,
        "mean_abs_delta": float(np.abs(np.diff(values)).mean()) if len(values) > 1 else 0.0,
        "std_value": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
        "unique_ratio": len(np.unique(values)) / len(values),
        "mean_value": float(values.mean()),
        "mean_interval_s": mean_i,
        "std_interval_s": std_i,
    }


def extract_features(device_id: str, sensor: str, window_size: int = WINDOW) -> dict:
    """Caractéristiques des `window_size` derniers messages du flux
    (device_id, sensor). Dict vide tant que la fenêtre n'est pas pleine."""
    rows = get_history(device_id, limit=window_size, sensor=sensor)
    if len(rows) < window_size:
        return {}
    rows = sorted(rows, key=lambda r: r["ts"])
    ts = np.array([_parse_ts(r["ts"]) for r in rows])
    values = np.array([r["value"] if r["value"] is not None else np.nan for r in rows], dtype=float)
    if np.isnan(values).any():
        return {}
    return window_features(ts, values)
