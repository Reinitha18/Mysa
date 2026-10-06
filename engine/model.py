"""
Détection d'anomalies comportementales : un modèle Isolation Forest est
entraîné séparément pour chaque appareil, sur ses propres caractéristiques
(engine/features.py). C'est ce qui permet à chaque appareil d'avoir sa propre
notion de "normal" plutôt qu'un seuil unique pour tout le foyer (voir
chapitre 5.2 du mémoire).

Chaque modèle est sauvegardé sur disque (engine/models/<device_id>.joblib)
pour ne pas avoir à ré-apprendre la baseline à chaque redémarrage.
"""

import os

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

FEATURE_ORDER = [
    "message_count",
    "mean_interval_s",
    "std_interval_s",
    "mean_value",
    "distinct_sensors",
    "seconds_since_last_message",
]


def _model_path(device_id: str) -> str:
    return os.path.join(MODELS_DIR, f"{device_id}.joblib")


def _to_vector(features: dict) -> list:
    return [features.get(key, 0.0) for key in FEATURE_ORDER]


def train_baseline(device_id: str, feature_history: list[dict]) -> bool:
    """Entraîne la baseline d'un appareil à partir d'un historique de vecteurs
    de caractéristiques (plusieurs appels à extract_features dans le temps).
    Retourne False si l'historique est encore insuffisant."""
    if len(feature_history) < 20:
        return False

    X = pd.DataFrame([_to_vector(f) for f in feature_history], columns=FEATURE_ORDER)
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X)
    joblib.dump(model, _model_path(device_id))
    return True


def score(device_id: str, features: dict) -> dict | None:
    """Évalue un nouveau vecteur de caractéristiques par rapport à la
    baseline de l'appareil. Retourne None si aucune baseline n'existe encore.
    `is_anomaly` vaut True si l'écart est jugé significatif."""
    path = _model_path(device_id)
    if not os.path.exists(path):
        return None

    model = joblib.load(path)
    X = pd.DataFrame([_to_vector(features)], columns=FEATURE_ORDER)
    raw_score = model.decision_function(X)[0]  # positif = normal, négatif = anormal
    is_anomaly = model.predict(X)[0] == -1

    return {"is_anomaly": bool(is_anomaly), "score": float(raw_score)}
