import numpy as np
from sklearn.ensemble import IsolationForest

from engine.fastforest import compile_forest, decision


def test_meme_score_que_scikit_learn():
    rng = np.random.default_rng(0)
    for n, d, contamination, max_features in [(40, 7, 0.01, 1.0), (200, 7, 0.05, 1.0), (120, 5, "auto", 0.6)]:
        X = rng.normal(size=(n, d)) * rng.uniform(0.01, 100, d)
        forest = IsolationForest(n_estimators=100, contamination=contamination, max_features=max_features,
                                 random_state=42).fit(X)
        compiled = compile_forest(forest)
        T = np.vstack([X, rng.normal(size=(200, d)) * 5 * X.std(0)])
        expected = forest.decision_function(T)
        got = np.array([decision(compiled, t) for t in T])
        assert np.allclose(expected, got, atol=1e-12)
        assert ((expected < 0) == (got < 0)).all()
