"""
Entraîne le modèle de référence d'UNE catégorie à partir d'un CSV public
(TON_IoT, télémétrie IoT) et l'évalue sur les fenêtres d'attaque du même CSV.

Usage :
  python scripts/train_reference.py --category mouvement --csv data/public/IoT_Motion_Light.csv
  python scripts/train_reference.py --category environnemental --csv data/public/IoT_Weather.csv \
         --value-col temperature

Sorties :
  engine/models/reference/<categorie>.joblib   (modèle + métadonnées)
  engine/models/reference/<categorie>.json     (métriques d'évaluation)

Une catégorie = un dataset = un modèle : on ne mélange jamais deux datasets.
"""

import argparse
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.categories import CATEGORY_DATASETS  # noqa: E402
from engine.features import PORTABLE_FEATURES, WINDOW, window_features  # noqa: E402
from engine.reference import REFERENCE_DIR  # noqa: E402


def to_epoch(df: pd.DataFrame, ts_col: str) -> pd.Series:
    """Horodatage en secondes. Accepte une colonne epoch numérique, ou les
    colonnes date + time des fichiers TON_IoT (ex. 31-Mar-19 / 12:36:52)."""
    if ts_col in df.columns:
        ts = pd.to_numeric(df[ts_col], errors="coerce")
        if ts.isna().mean() <= 0.5:
            return ts
    if {"date", "time"} <= set(df.columns):
        months = {m: i for i, m in enumerate(
            ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
        parts = df["date"].astype(str).str.strip().str.split("-", expand=True)
        if parts.shape[1] == 3:  # format JJ-Mon-AA, indépendant de la langue du système
            day = pd.to_numeric(parts[0], errors="coerce")
            mon = parts[1].str.lower().str[:3].map(months)
            year = pd.to_numeric(parts[2], errors="coerce")
            year = year.where(year >= 100, 2000 + year)
            dt = pd.to_datetime(pd.DataFrame({"year": year, "month": mon, "day": day}), errors="coerce")
            dt = dt + pd.to_timedelta(df["time"].astype(str), errors="coerce")
            if dt.isna().mean() <= 0.5:
                return (dt - pd.Timestamp("1970-01-01")).dt.total_seconds()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dt = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), errors="coerce")
        return (dt - pd.Timestamp("1970-01-01")).dt.total_seconds()
    raise SystemExit(f"Aucun horodatage exploitable : colonne '{ts_col}' ou date+time absentes. "
                     f"Colonnes du fichier : {list(df.columns)}")


def load_series(csv_path: str, value_col: str, ts_col: str, label_col: str):
    df = pd.read_csv(csv_path)
    for col in (value_col, label_col):
        if col not in df.columns:
            raise SystemExit(f"Colonne '{col}' introuvable. Colonnes du fichier : {list(df.columns)}")
    ts = to_epoch(df, ts_col)
    values = pd.to_numeric(df[value_col], errors="coerce")
    if values.isna().mean() > 0.5:  # valeurs textuelles (open/closed, on/off...) -> codes
        values = pd.Series(pd.factorize(df[value_col].astype(str), sort=True)[0], index=df.index)
    out = pd.DataFrame({"ts": ts, "value": values, "label": pd.to_numeric(df[label_col], errors="coerce")})
    # Tri STABLE : à horodatage égal, l'ordre du fichier est conservé.
    return out.dropna().sort_values("ts", kind="stable").reset_index(drop=True)


def make_windows(df: pd.DataFrame, stride: int, features=None):
    """Fenêtres de WINDOW lignes consécutives -> (X portable, part de lignes d'attaque)."""
    features = features or PORTABLE_FEATURES
    rows, attack_share = [], []
    for start in range(0, len(df) - WINDOW + 1, stride):
        w = df.iloc[start:start + WINDOW]
        f = window_features(w["ts"].to_numpy(), w["value"].to_numpy())
        rows.append([f[c] for c in features])
        attack_share.append(float(w["label"].mean()))
    return pd.DataFrame(rows, columns=features), np.array(attack_share)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", required=True, choices=sorted(CATEGORY_DATASETS))
    ap.add_argument("--csv", required=True)
    ap.add_argument("--value-col", default=None)
    ap.add_argument("--ts-col", default="ts")
    ap.add_argument("--label-col", default="label")
    ap.add_argument("--contamination", type=float, default=0.05)
    args = ap.parse_args()

    value_col = args.value_col or CATEGORY_DATASETS[args.category]["value_col"]
    df = load_series(args.csv, value_col, args.ts_col, args.label_col)
    # Windows non chevauchantes : évite des échantillons quasi identiques.
    X, attack = make_windows(df, stride=WINDOW)

    normal_idx = np.where(attack == 0)[0]
    attack_idx = np.where(attack >= 0.5)[0]
    rng = np.random.default_rng(42)
    rng.shuffle(normal_idx)
    cut = int(0.8 * len(normal_idx))
    train_idx, test_normal_idx = normal_idx[:cut], normal_idx[cut:]

    model = IsolationForest(n_estimators=100, contamination=args.contamination, random_state=42)
    model.fit(X.iloc[train_idx])

    def flagged(idx):
        return float((model.predict(X.iloc[idx]) == -1).mean()) if len(idx) else None

    metrics = {
        "category": args.category, "dataset": os.path.basename(args.csv), "value_col": value_col,
        "window": WINDOW, "features": PORTABLE_FEATURES,
        "n_windows_train": int(len(train_idx)),
        "n_windows_test_normal": int(len(test_normal_idx)),
        "n_windows_test_attack": int(len(attack_idx)),
        "false_positive_rate": flagged(test_normal_idx),
        "detection_rate": flagged(attack_idx),
    }
    os.makedirs(REFERENCE_DIR, exist_ok=True)
    joblib.dump({"model": model, "features": PORTABLE_FEATURES, "category": args.category,
                 "window": WINDOW, "source": metrics["dataset"]},
                os.path.join(REFERENCE_DIR, f"{args.category}.joblib"))
    with open(os.path.join(REFERENCE_DIR, f"{args.category}.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()