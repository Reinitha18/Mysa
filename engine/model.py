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
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from engine.features import LOCAL_FEATURES

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# 40 échantillons minimum : avec 20, le modèle signale à tort plus de 15 % des fenêtres
# d'un flux stationnaire (mesure sur flux simulé), contre environ 10 % avec 40.
MIN_TRAIN_SAMPLES = 40
CONTAMINATION = 0.01

# Enveloppe de plausibilité. Isolation Forest ne sait pas extrapoler : une valeur très au-delà
# de ce qu'il a vu à l'entraînement n'est pas isolée plus vite que les points extrêmes de
# l'entraînement (un pic isolé n'est détecté que dans 20 à 40 % des cas, mesure sur flux simulé).
# L'enveloppe signale toute fenêtre dont une caractéristique de valeurs sort de la plage
# d'entraînement de plus de ENVELOPE_K fois son étendue (avec un plancher de 5 % de l'amplitude).
ENVELOPE_FEATURES = ["mean_abs_delta", "std_value", "unique_ratio", "mean_value"]
ENVELOPE_K = 5.0


def _model_path(key: str) -> str:
    return os.path.join(MODELS_DIR, f"{key}.joblib")


def has_baseline(key: str) -> bool:
    return os.path.exists(_model_path(key))


def _to_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([[r[c] for c in LOCAL_FEATURES] for r in rows], columns=LOCAL_FEATURES)


def _envelope(X: pd.DataFrame, binary: bool = False) -> dict:
    lo, hi = X[ENVELOPE_FEATURES].min().to_numpy(), X[ENVELOPE_FEATURES].max().to_numpy()
    magnitude = np.maximum(np.abs(lo), np.abs(hi))
    span = np.maximum(np.maximum(hi - lo, 0.05 * magnitude), 1e-6)
    if binary:
        # Capteur binaire (unité « bool ») : un événement rare jamais vu à l'entraînement (une porte
        # qui s'ouvre pour la première fois) est normal. L'enveloppe ne sert alors qu'à repérer une
        # valeur hors du domaine 0/1 ; les motifs inhabituels restent l'affaire de la forêt.
        span = np.maximum(span, 1.0)
    return {"lo": lo, "hi": hi, "span": span}


def train_baseline(key: str, feature_history: list[dict], binary: bool = False) -> bool:
    """(Ré)entraîne le modèle local du flux. False si historique insuffisant."""
    if len(feature_history) < MIN_TRAIN_SAMPLES:
        return False
    X = _to_frame(feature_history)
    forest = IsolationForest(n_estimators=100, contamination=CONTAMINATION, random_state=42).fit(X)
    joblib.dump({"forest": forest, "envelope": _envelope(X, binary)}, _model_path(key))
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
    """Évalue un vecteur par rapport au modèle local (None si pas de modèle).
    Retourne is_anomaly, score et reason ("forêt" ou "enveloppe")."""
    path = _model_path(key)
    if not os.path.exists(path):
        return None
    bundle = _load(path)
    if not isinstance(bundle, dict):  # ancien format : forêt seule, sans enveloppe
        bundle = {"forest": bundle, "envelope": None}
    X = _to_frame([features])
    forest = bundle["forest"]
    forest_flag = bool(forest.predict(X)[0] == -1)
    env = bundle["envelope"]
    env_flag = False
    if env is not None:
        v = X[ENVELOPE_FEATURES].to_numpy()[0]
        env_flag = bool(((v > env["hi"] + ENVELOPE_K * env["span"]) | (v < env["lo"] - ENVELOPE_K * env["span"])).any())
    return {
        "is_anomaly": forest_flag or env_flag,
        "score": float(forest.decision_function(X)[0]),
        "reason": "enveloppe" if env_flag else ("forêt" if forest_flag else None),
    }
