"""
Évaluation d'un modèle de référence par INJECTION d'anomalies de valeurs.

Les étiquettes d'attaque de TON_IoT ne se traduisent pas dans les valeurs des
capteurs (voir diag_reference.py). Pour mesurer ce que la référence sait vraiment
détecter, on prend les fenêtres NORMALES de TEST (jamais vues à l'entraînement,
même découpage que train_reference.py), on y injecte une anomalie synthétique de
valeurs, et on mesure la part de fenêtres signalées. Les paramètres des anomalies
sont fixés ici une fois pour toutes, et ne sont pas réglés sur les résultats.

IMPORTANT : l'injection est SYNTHÉTIQUE. Elle mesure la sensibilité à des types
d'anomalies définis a priori, pas la performance face à de vraies attaques.

Usage : python scripts/eval_injection.py --category mouvement --csv data/public/IoT_Motion_Light.csv
"""
import argparse
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_reference import check_pairing, load_series, make_windows, split_indices  # noqa: E402
from engine.categories import CATEGORY_DATASETS  # noqa: E402
from engine.features import PORTABLE_FEATURES, WINDOW, window_features  # noqa: E402
from engine.reference import reference_path  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--category", required=True, choices=sorted(CATEGORY_DATASETS))
ap.add_argument("--csv", required=True)
ap.add_argument("--value-col", default=None)
ap.add_argument("--force", action="store_true")
args = ap.parse_args()
check_pairing(args.category, args.csv, args.force)

value_col = args.value_col or CATEGORY_DATASETS[args.category]["value_col"]
df = load_series(args.csv, value_col, "ts", "label")
_, share = make_windows(df, stride=WINDOW)
_, test_idx, _ = split_indices(share)

vals, ts = df["value"].to_numpy(float), df["ts"].to_numpy(float)
normal_vals = vals[df["label"].to_numpy() == 0]
g_mean, g_std = normal_vals.mean(), normal_vals.std()
v_min, v_max = normal_vals.min(), normal_vals.max()
bundle = joblib.load(reference_path(args.category))
model = bundle["model"]
rng = np.random.default_rng(7)  # graine fixe : résultats reproductibles


def spike(k):
    def f(v):
        v = v.copy()
        v[rng.integers(len(v))] = g_mean + k * g_std
        return v
    return f


ANOMALIES = {
    "pic (8 écarts-types)": spike(8),
    "pic (4 écarts-types)": spike(4),
    "valeur bloquée": lambda v: np.full_like(v, v[0]),
    "oscillation extrême": lambda v: np.where(np.arange(len(v)) % 2 == 0, v_min, v_max),
    "décalage de niveau (+4 écarts-types)": lambda v: v + 4 * g_std,
}


def flagged_rate(transform):
    rows = []
    for i in test_idx:
        sl = slice(i * WINDOW, (i + 1) * WINDOW)
        v = vals[sl] if transform is None else transform(vals[sl])
        f = window_features(ts[sl], v)
        rows.append([f[c] for c in PORTABLE_FEATURES])
    X = pd.DataFrame(rows, columns=PORTABLE_FEATURES)
    return float((model.predict(X) == -1).mean())


constant_share = float(np.mean([np.ptp(vals[i * WINDOW:(i + 1) * WINDOW]) == 0 for i in test_idx]))
result = {"category": args.category, "dataset": os.path.basename(args.csv), "n_test_windows": int(len(test_idx)),
          "windows_already_constant_share": constant_share,
          "reference_false_alarm_rate": flagged_rate(None), "detection_by_anomaly": {}}
for name, fn in ANOMALIES.items():
    result["detection_by_anomaly"][name] = flagged_rate(fn)

print(f"\nCatégorie : {args.category}  ({len(test_idx)} fenêtres normales de test)")
print(f"Fausses alertes (sans injection)          : {result['reference_false_alarm_rate']:.1%}")
print(f"Part de fenêtres normales déjà constantes : {constant_share:.1%}")
print("\nDétection par type d'anomalie injectée :")
for name, r in result["detection_by_anomaly"].items():
    print(f"   {name:<40} {r:6.1%}")
print("\nNote : injection synthétique ; paramètres fixés a priori (8 et 4 écarts-types, oscillation min/max, +4 écarts-types).")
out = os.path.join(os.path.dirname(reference_path(args.category)), f"{args.category}.injection.json")
with open(out, "w") as fh:
    json.dump(result, fh, indent=2, ensure_ascii=False)
