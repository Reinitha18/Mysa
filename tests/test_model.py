import numpy as np

from engine import model


def _normal(rng, n=120, slope_scale=0.002):
    return [{"mean_abs_delta": rng.uniform(0.08, 0.12), "std_value": rng.uniform(0.1, 0.15),
             "unique_ratio": rng.uniform(0.5, 0.7), "cv_interval": rng.uniform(0.0, 0.05),
             "mean_value": rng.uniform(23.5, 24.5), "mean_interval_s": rng.uniform(2.9, 3.1),
             "std_interval_s": rng.uniform(0.0, 0.1), "trend_slope": rng.normal(0, slope_scale)}
            for _ in range(n)]


def test_detecteurs_du_modele_local():
    rng = np.random.default_rng(1)
    assert model.train_baseline("flux", _normal(rng))
    normal = _normal(rng, 1)[0]
    r = model.score("flux", normal)
    assert not r["is_anomaly"]

    spike = {**normal, "mean_abs_delta": 50.0, "std_value": 30.0, "mean_value": 70.0}
    assert model.score("flux", spike)["reason"] == "enveloppe"

    flood = {**normal, "mean_interval_s": 0.1}
    r = model.score("flux", flood)
    assert r["is_anomaly"] and r["strong"] and r["reason"] == "rythme"

    drift = {**normal, "trend_slope": 0.05}
    r = model.score("flux", drift)
    assert r["is_anomaly"] and r["reason"] == "tendance" and r["strong"]


def test_tendance_desactivee_pour_capteur_binaire():
    rng = np.random.default_rng(2)
    assert model.train_baseline("pir", _normal(rng), binary=True)
    normal = _normal(rng, 1)[0]
    assert not model.score("pir", {**normal, "trend_slope": 1.0})["is_anomaly"]


def test_historique_insuffisant():
    assert not model.train_baseline("x", _normal(np.random.default_rng(3), n=10))
    assert model.score("x", _normal(np.random.default_rng(3), 1)[0]) is None
