import json

import pytest

from engine import ingest
from engine.ingest import Rejected, parse_message

NOW = "2026-01-01T00:00:00+00:00"


def msg(**kw):
    return json.dumps(kw).encode()


def test_message_valide_et_conversions():
    m = parse_message("home/esp32-sec-01/pir", msg(value=True, unit="bool"), NOW)
    assert m == {"device_id": "esp32-sec-01", "sensor": "pir", "value": 1.0, "unit": "bool", "ts": NOW, "meta": {}}
    assert parse_message("home/a/t", msg(value="21,5"), NOW)["value"] == 21.5


def test_topic_fait_foi_contre_usurpation():
    with pytest.raises(Rejected, match="usurpation"):
        parse_message("home/esp32-sec-01/pir", msg(device_id="esp32-cmf-01", sensor="pir", value=1), NOW)


@pytest.mark.parametrize("topic,raw", [
    ("home/a/b", b"pas du json"),
    ("home/a/b", b"[1, 2]"),
    ("home/a/b", msg(value="ouvert")),
    ("home/a/b", msg(unit="C")),
    ("maison/a/b", msg(value=1)),
    ("home/a/b/c", msg(value=1)),
])
def test_messages_rejetes(topic, raw):
    with pytest.raises(Rejected):
        parse_message(topic, raw, NOW)


def test_commandes_ignorees():
    assert parse_message("home/esp32-cmf-01/cmd/relay", b"on", NOW) is None


def test_horodatage_sans_fuseau_ramene_en_utc(monkeypatch):
    monkeypatch.setattr(ingest, "TRUST_DEVICE_TS", True)  # indépendant du .env local
    m = parse_message("home/a/b", msg(value=1, ts="2026-01-01T10:00:00"), NOW)
    assert m["ts"] == "2026-01-01T10:00:00+00:00"
    assert parse_message("home/a/b", msg(value=1, ts="n'importe quoi"), NOW)["ts"] == NOW
