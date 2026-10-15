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


def load_series(csv_path: str, value_col: str, ts_col: str, label_col: str):
    df = pd.read_csv(csv_path)
    ts = pd.to_numeric(df[ts_col], errors="coerce")
    if ts.isna().mean() > 0.5:  # pas de epoch numérique : on parse date + time
        ts = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str),
                            errors="coerce").astype("int64") / 1e9
    values = pd.to_numeric(df[value_col], errors="coerce")
    if values.isna().mean() > 0.5:  # valeurs textuelles (open/closed, on/off...) -> codes
        values = pd.Series(pd.factorize(df[value_col].astype(str), sort=True)[0], index=df.index)
    out = pd.DataFrame({"ts": ts, "value": values, "label": pd.to_numeric(df[label_col], errors="coerce")})
    return out.dropna().sort_values("ts").reset_index(drop=True)


def make_windows(df: pd.DataFrame, stride: int):
    """Fenêtres de WINDOW lignes consécutives -> (X portable, part de lignes d'attaque)."""
    rows, attack_share = [], []
    for start in range(0, len(df) - WINDOW + 1, stride):
        w = df.iloc[start:start + WINDOW]
        f = window_features(w["ts"].to_numpy(), w["value"].to_numpy())
        rows.append([f[c] for c in PORTABLE_FEATURES])
        attack_share.append(float(w["label"].mean()))
    return pd.DataFrame(rows, columns=PORTABLE_FEATURES), np.array(attack_share)


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
