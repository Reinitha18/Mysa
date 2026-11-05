from datetime import datetime, timedelta, timezone

from engine import risk
from engine.storage import insert_alert, mark_silent, record_message


def test_score_et_decroissance():
    assert risk.risk_score([]) == 0
    assert risk.risk_score([("high", 0)]) == 40
    assert risk.risk_score([("high", 0)] * 5) == 100
    assert risk.risk_score([("high", risk.TAU_S)]) == round(40 / 2.718281828)
    assert risk.level(10)[0] == "normal" and risk.level(30)[0] == "à surveiller" and risk.level(80)[0] == "critique"


def test_episodes_et_non_alertes_brutes():
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    for i in reversed(range(10)):  # 10 alertes rapprochées, dans l'ordre chronologique = 1 seul épisode
        insert_alert("cam", "x", severity="high", ts=(now - timedelta(seconds=10 * i)).isoformat(),
                     sensor="bitrate", kind="anomaly")
    r = risk.device_risks(now=now)["cam"]
    assert r["score"] == 40 and r["level"] == "à surveiller" and len(r["causes"]) == 1


def test_flux_silencieux():
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    record_message("pir1", "pir", 0, "bool", now.isoformat())
    mark_silent("pir1", "pir")
    r = risk.device_risks(now=now, device_id="pir1")["pir1"]
    assert r["score"] == risk.SILENT_WEIGHT and r["silent_sensors"] == ["pir"]
