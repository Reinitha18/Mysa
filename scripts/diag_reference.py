"""
Diagnostic d'un modèle de référence : les fenêtres d'attaque du dataset sont-elles
différentes des fenêtres normales ? Et le modèle les distingue-t-il ?

Usage : python scripts/diag_reference.py --category mouvement --csv data/public/IoT_Motion_Light.csv
"""
import argparse
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_reference import load_series, make_windows  # noqa: E402
from engine.categories import CATEGORY_DATASETS  # noqa: E402
from engine.features import LOCAL_FEATURES, PORTABLE_FEATURES, WINDOW  # noqa: E402
from engine.reference import reference_path  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--category", required=True)
ap.add_argument("--csv", required=True)
ap.add_argument("--value-col", default=None)
args = ap.parse_args()

value_col = args.value_col or CATEGORY_DATASETS[args.category]["value_col"]
df = load_series(args.csv, value_col, "ts", "label")
t = pd.to_datetime(df["ts"], unit="s")
d = df["ts"].diff().dropna()
print(f"Période couverte : {t.min()} -> {t.max()}  ({len(df)} lignes)")
print(f"Lignes consécutives à horodatage identique : {(d == 0).mean():.1%} ; pas médian {d.median():.1f} s")
print("Par classe — part d'horodatages identiques (lignes d'une même seconde) :")
print(f"   normal : {(d[df['label'].iloc[1:] == 0] == 0).mean():.1%}   attaque : {(d[df['label'].iloc[1:] == 1] == 0).mean():.1%}")

XL, share = make_windows(df, stride=WINDOW, features=LOCAL_FEATURES)
X = XL[PORTABLE_FEATURES]
normal, attack = share == 0, share >= 0.5
print(f"\nFenêtres : {normal.sum()} normales, {attack.sum()} d'attaque, {(~normal & ~attack).sum()} mixtes (écartées)")

print("\nMédiane et moyenne des caractéristiques, par classe :")
summary = pd.DataFrame({
    "normal_médiane": XL[normal].median(), "attaque_médiane": XL[attack].median(),
    "normal_moyenne": XL[normal].mean(), "attaque_moyenne": XL[attack].mean(),
}).round(3)
print(summary.to_string())

bundle = joblib.load(reference_path(args.category))
sc = bundle["model"].decision_function(X[normal | attack][PORTABLE_FEATURES])
y = attack[normal | attack].astype(int)
auc = roc_auc_score(y, -sc)  # score élevé = plus anormal
print(f"\nAUC (séparation normal/attaque par le modèle) : {auc:.3f}   (0,5 = aucune séparation ; <0,5 = inversé)")

print("\nSéparation caractéristique par caractéristique (AUC ramenée à >= 0,5 ; 0,5 = aucune) :")
yy = attack[normal | attack].astype(int)
for c in LOCAL_FEATURES:
    a = roc_auc_score(yy, XL.loc[normal | attack, c])
    print(f"   {c:<16} {max(a, 1 - a):.3f}  ({'portable' if c in PORTABLE_FEATURES else 'locale'})")
print("\nNote : ce diagnostic sert à COMPRENDRE le dataset ; il ne sert pas à choisir les caractéristiques du modèle sur la base des étiquettes d'attaque.")