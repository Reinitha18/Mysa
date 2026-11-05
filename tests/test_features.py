import numpy as np

from engine import features as feat
from engine.storage import record_message


def test_pente_theil_sen_insensible_a_un_pic():
    ts = np.arange(40) * 3.0
    values = 20 + 0.01 * ts
    spiked = values.copy()
    spiked[25] = 999
    assert abs(feat.trend_slope(ts, values) - 0.01) < 1e-9
    assert abs(feat.trend_slope(ts, spiked) - 0.01) < 1e-3


def test_fenetre_incomplete_puis_pente_disponible():
    for i in range(feat.WINDOW - 1):
        record_message("d", "t", 20.0, "C", f"2026-01-01T00:{i // 20:02d}:{(i * 3) % 60:02d}+00:00")
    assert feat.extract_features("d", "t") == {}
    for i in range(feat.WINDOW - 1, feat.TREND_WINDOW):
        record_message("d", "t", 20.0 + i * 0.1, "C", f"2026-01-01T{i * 3 // 3600:02d}:{i * 3 // 60 % 60:02d}:{i * 3 % 60:02d}+00:00")
    f = feat.extract_features("d", "t")
    assert set(feat.LOCAL_FEATURES) <= set(f)
    assert f["trend_slope"] > 0
