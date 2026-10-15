"""
Modèles de référence par catégorie d'appareil (amorçage à froid).

Chaque modèle est un Isolation Forest entraîné par scripts/train_reference.py
sur le dataset public d'UNE catégorie, uniquement sur les fenêtres de
télémétrie normale, avec les caractéristiques PORTABLES (engine/features.py).
Il sert de filet de sécurité tant que le modèle local d'un flux n'est pas
prêt ; il n'est jamais mélangé avec un autre.
"""

import os

import joblib
import pandas as pd

REFERENCE_DIR = os.path.join(os.path.dirname(__file__), "models", "reference")
_cache: dict[str, dict | None] = {}


def reference_path(category: str) -> str:
    return os.path.join(REFERENCE_DIR, f"{category}.joblib")


def load_reference(category: str | None) -> dict | None:
    """Charge le modèle de référence d'une catégorie (None si absent)."""
    if not category:
        return None
    if category not in _cache:
        path = reference_path(category)
        _cache[category] = joblib.load(path) if os.path.exists(path) else None
    return _cache[category]


def score_reference(bundle: dict, features: dict) -> dict:
    cols = bundle["features"]
    X = pd.DataFrame([[features[c] for c in cols]], columns=cols)
    model = bundle["model"]
    return {
        "is_anomaly": bool(model.predict(X)[0] == -1),
        "score": float(model.decision_function(X)[0]),
    }
