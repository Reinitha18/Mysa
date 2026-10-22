"""
Modèle LOCAL de détection d'anomalies : un Isolation Forest par flux capteur
(appareil + capteur), appris sur la télémétrie réelle de ce flux avec le jeu
complet de caractéristiques (engine/features.py : LOCAL_FEATURES).

Isolation Forest ne se « fine-tune » pas (pas de partial_fit) : l'affinage
consiste à ré-entraîner périodiquement le modèle sur une fenêtre glissante des
échantillons récents jugés normaux (voir engine/analyzer.py).

Chaque modèle est sauvegardé (engine/models/<clé>.joblib) pour survivre à un
redémarrage du moteur.
"""

import os

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

from engine.features import LOCAL_FEATURES

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

MIN_TRAIN_SAMPLES = 20


def _model_path(key: str) -> str:
    return os.path.join(MODELS_DIR, f"{key}.joblib")


def has_baseline(key: str) -> bool:
    return os.path.exists(_model_path(key))


def _to_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([[r[c] for c in LOCAL_FEATURES] for r in rows], columns=LOCAL_FEATURES)


def train_baseline(key: str, feature_history: list[dict]) -> bool:
    """(Ré)entraîne le modèle local du flux. False si historique insuffisant."""
    if len(feature_history) < MIN_TRAIN_SAMPLES:
        return False
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(_to_frame(feature_history))
    joblib.dump(model, _model_path(key))
    return True


_cache: dict[str, tuple[float, object]] = {}


def _load(path: str):
    """Charge un modèle en mémoire et ne le relit que si le fichier a changé."""
    mtime = os.path.getmtime(path)
    cached = _cache.get(path)
    if cached is None or cached[0] != mtime:
        _cache[path] = (mtime, joblib.load(path))
    return _cache[path][1]


def score(key: str, features: dict) -> dict | None:
    """Évalue un vecteur par rapport au modèle local (None si pas de modèle)."""
    path = _model_path(key)
    if not os.path.exists(path):
        return None
    model = _load(path)
    X = _to_frame([features])
    return {
        "is_anomaly": bool(model.predict(X)[0] == -1),
        "score": float(model.decision_function(X)[0]),
    }
