"""
Modèle LOCAL de détection d'anomalies d'un flux capteur (appareil + capteur), appris
sur la télémétrie réelle de ce flux. Il combine quatre détecteurs, chacun avec un rôle
précis :

  - FORÊT (Isolation Forest, LOCAL_FEATURES) : combinaisons inhabituelles de
    caractéristiques. Son seuil est CALIBRÉ sur les scores d'entraînement (voir
    FOREST_MARGIN) et non sur le seul paramètre de contamination : avec 40 à 200
    fenêtres très corrélées, le quantile à 1 % est instable et produisait la majorité
    des fausses alertes (scores à peine négatifs). Indice faible : à confirmer.
  - ENVELOPPE DE VALEURS : une caractéristique de valeurs très au-delà de la plage
    d'entraînement (pic, valeur hors domaine). Isolation Forest ne sait pas extrapoler :
    ces cas lui échappent. Indice fort.
  - ENVELOPPE DE RYTHME : intervalle moyen entre messages hors de la plage d'entraînement
    d'un facteur RATE_FACTOR (inondation, ralentissement). Indice fort.
  - TENDANCE (capteurs continus seulement) : pente des valeurs sur une longue fenêtre
    (features.TREND_WINDOW) bien plus forte que toutes celles vues à l'entraînement
    (dérive progressive, SC-03). Indice fort.
  - BASCULES (capteurs binaires seulement) : taux de changement d'état (mean_abs_delta)
    bien au-delà de l'entraînement (capteur qui oscille, SC-06). L'enveloppe de valeurs est
    volontairement large pour les capteurs binaires et ne voit pas ce cas. Indice fort.

Isolation Forest ne se « fine-tune » pas (pas de partial_fit) : l'affinage consiste à
ré-entraîner périodiquement le modèle sur une fenêtre glissante des échantillons récents
jugés normaux (voir engine/analyzer.py).

Chaque modèle est sauvegardé (MYSA_MODELS_DIR, par défaut engine/models/<clé>.joblib)
pour survivre à un redémarrage du moteur. L'évaluation passe par engine/fastforest.py.
"""

import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from engine.fastforest import compile_forest, decision
from engine.features import LOCAL_FEATURES

MODELS_DIR = os.getenv("MYSA_MODELS_DIR") or os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# 40 échantillons minimum : avec 20, le modèle signale à tort plus de 15 % des fenêtres
# d'un flux stationnaire (mesure sur flux simulé), contre environ 10 % avec 40.
MIN_TRAIN_SAMPLES = 40
CONTAMINATION = 0.01

# Seuil de la forêt : une fenêtre n'est suspecte que si son score est plus bas que le plus bas
# des scores d'entraînement, d'une marge de FOREST_MARGIN fois l'écart (médiane - minimum).
FOREST_MARGIN = 0.5

# Enveloppe de valeurs : signale une caractéristique qui sort de la plage d'entraînement de
# plus de ENVELOPE_K fois son étendue (avec un plancher de 5 % de l'amplitude).
ENVELOPE_FEATURES = ["mean_abs_delta", "std_value", "unique_ratio", "mean_value"]
ENVELOPE_K = 5.0

# Enveloppe de rythme : intervalle moyen hors de [min / RATE_FACTOR, max x RATE_FACTOR].
RATE_FACTOR = 3.0

# Tendance : |pente| > TREND_K x la plus forte |pente| d'entraînement (plancher TREND_FLOOR_K
# fois la pente que produirait le bruit de mesure habituel sur la durée de la fenêtre).
TREND_K = 2.0
TREND_FLOOR_K = 3.0

# Bascules : taux de changement d'état > max(TOGGLE_K x maximum d'entraînement, TOGGLE_MIN).
TOGGLE_K = 2.0
TOGGLE_MIN = 0.5

STRONG_REASONS = ("enveloppe", "rythme", "tendance", "bascules")


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


def _rate_envelope(X: pd.DataFrame) -> dict | None:
    intervals = X["mean_interval_s"].to_numpy()
    intervals = intervals[intervals > 0]
    if not len(intervals):
        return None
    return {"lo": float(intervals.min()) / RATE_FACTOR, "hi": float(intervals.max()) * RATE_FACTOR}


def _trend_limit(rows: list[dict], X: pd.DataFrame, binary: bool) -> float | None:
    """Pente maximale tolérée (unités par seconde), ou None si la tendance ne s'applique pas."""
    slopes = np.array([abs(r["trend_slope"]) for r in rows if r.get("trend_slope") is not None])
    if binary or len(slopes) < MIN_TRAIN_SAMPLES // 2:
        return None
    # Pente que le seul bruit de mesure peut produire : écart-type habituel / durée d'une fenêtre.
    duration = float(np.median(X["mean_interval_s"])) * 20.0
    noise_slope = float(np.median(X["std_value"])) / duration if duration > 0 else 0.0
    return max(TREND_K * float(slopes.max()), TREND_FLOOR_K * noise_slope, 1e-9)


def train_baseline(key: str, feature_history: list[dict], binary: bool = False) -> bool:
    """(Ré)entraîne le modèle local du flux. False si historique insuffisant."""
    if len(feature_history) < MIN_TRAIN_SAMPLES:
        return False
    X = _to_frame(feature_history)
    forest = IsolationForest(n_estimators=100, contamination=CONTAMINATION, random_state=42).fit(X)
    d = forest.decision_function(X)
    threshold = min(0.0, float(d.min()) - FOREST_MARGIN * float(np.median(d) - d.min()))
    bundle = {"forest": forest, "threshold": threshold, "envelope": _envelope(X, binary),
              "rate": _rate_envelope(X), "trend": _trend_limit(feature_history, X, binary),
              "toggle": max(TOGGLE_K * float(X["mean_abs_delta"].max()), TOGGLE_MIN) if binary else None,
              "binary": binary, "n_train": len(feature_history)}
    tmp = _model_path(key) + ".tmp"
    joblib.dump(bundle, tmp)
    os.replace(tmp, _model_path(key))  # écriture atomique : l'API ne lit jamais un fichier à moitié écrit
    return True


_cache: dict[str, tuple[float, object]] = {}


def _load(path: str):
    """Charge un modèle en mémoire et ne le relit que si le fichier a changé."""
    mtime = os.path.getmtime(path)
    cached = _cache.get(path)
    if cached is None or cached[0] != mtime:
        bundle = joblib.load(path)
        if not isinstance(bundle, dict):  # ancien format : forêt seule, sans enveloppe
            bundle = {"forest": bundle, "envelope": None}
        bundle.setdefault("threshold", 0.0)  # modèles de l'ancienne version : seuil d'origine
        bundle["compiled"] = compile_forest(bundle["forest"])
        _cache[path] = (mtime, bundle)
    return _cache[path][1]


def score(key: str, features: dict) -> dict | None:
    """Évalue un vecteur par rapport au modèle local (None si pas de modèle).

    Retourne is_anomaly, score (forêt, négatif = suspect), threshold, reason
    ("enveloppe", "rythme", "tendance", "bascules", "forêt" ou None) et strong (indice fort)."""
    path = _model_path(key)
    if not os.path.exists(path):
        return None
    bundle = _load(path)
    s = decision(bundle["compiled"], [features[c] for c in LOCAL_FEATURES])
    reasons = []

    env = bundle.get("envelope")
    if env is not None:
        v = np.array([features[c] for c in ENVELOPE_FEATURES], dtype=float)
        if ((v > env["hi"] + ENVELOPE_K * env["span"]) | (v < env["lo"] - ENVELOPE_K * env["span"])).any():
            reasons.append("enveloppe")
    rate = bundle.get("rate")
    if rate is not None and features["mean_interval_s"] > 0:
        if not rate["lo"] <= features["mean_interval_s"] <= rate["hi"]:
            reasons.append("rythme")
    limit = bundle.get("trend")
    if limit is not None and features.get("trend_slope") is not None and abs(features["trend_slope"]) > limit:
        reasons.append("tendance")
    toggle = bundle.get("toggle")
    if toggle is not None and features["mean_abs_delta"] > toggle:
        reasons.append("bascules")
    if s < bundle["threshold"]:
        reasons.append("forêt")

    return {
        "is_anomaly": bool(reasons),
        "score": float(s),
        "threshold": float(bundle["threshold"]),
        "reason": reasons[0] if reasons else None,
        "strong": any(r in STRONG_REASONS for r in reasons),
    }
