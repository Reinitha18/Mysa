"""
Évaluation rapide d'un Isolation Forest scikit-learn sur UN échantillon.

Pourquoi : le moteur évalue une seule fenêtre à chaque message reçu. Pour un seul
échantillon, `IsolationForest.decision_function` coûte environ 30 ms (surcoût de
répartition des 100 arbres via joblib), et l'ancien code l'appelait deux fois par
message (predict + decision_function). Ici, les arbres entraînés sont « compilés »
une fois en tableaux numpy, puis parcourus directement : même résultat, environ
cent fois plus vite.

Le modèle reste un IsolationForest scikit-learn standard (entraînement, sauvegarde
joblib inchangés) : seule l'évaluation est réécrite, à partir des attributs publics
des arbres (tree_.children_left, feature, threshold, n_node_samples). L'égalité avec
scikit-learn est vérifiée par tests/test_fastforest.py.
"""

import numpy as np


def _average_path_length(n: np.ndarray) -> np.ndarray:
    """c(n) : longueur moyenne d'un chemin dans un arbre binaire de n points
    (même formule que sklearn.ensemble._iforest._average_path_length)."""
    n = np.asarray(n, dtype=float)
    out = np.zeros_like(n)
    out[n == 2] = 1.0
    big = n > 2
    out[big] = 2.0 * (np.log(n[big] - 1.0) + np.euler_gamma) - 2.0 * (n[big] - 1.0) / n[big]
    return out


def compile_forest(forest) -> dict:
    """Extrait d'un IsolationForest entraîné ce qu'il faut pour le parcourir."""
    trees = []
    n_features = forest.n_features_in_
    for est, feats in zip(forest.estimators_, forest.estimators_features_):
        t = est.tree_
        left, right = t.children_left, t.children_right
        depth = np.zeros(t.node_count, dtype=float)  # nombre de nœuds sur le chemin (racine = 1)
        depth[0] = 1.0
        for node in range(t.node_count):  # les enfants ont toujours un indice supérieur au parent
            if left[node] != -1:
                depth[left[node]] = depth[right[node]] = depth[node] + 1.0
        leaf_value = depth + _average_path_length(t.n_node_samples) - 1.0
        # Même règle que scikit-learn : sous-ensemble de variables seulement si max_features < n.
        cols = np.asarray(feats) if len(feats) != n_features else None
        trees.append((left.tolist(), right.tolist(), t.feature.tolist(),
                      t.threshold.tolist(), leaf_value.tolist(), cols))
    return {"trees": trees, "denominator": len(trees) * float(_average_path_length([forest.max_samples_])[0]),
            "offset": float(forest.offset_)}


def decision(compiled: dict, x) -> float:
    """Équivalent de forest.decision_function([x])[0] : négatif = anomalie."""
    x32 = np.asarray(x, dtype=np.float32).astype(float)  # scikit-learn compare en float32
    total = 0.0
    for left, right, feature, threshold, leaf_value, cols in compiled["trees"]:
        v = x32 if cols is None else x32[cols]
        node = 0
        while left[node] != -1:
            node = left[node] if v[feature[node]] <= threshold[node] else right[node]
        total += leaf_value[node]
    den = compiled["denominator"]
    score = 2.0 ** (-total / den) if den else 1.0
    return -score - compiled["offset"]
