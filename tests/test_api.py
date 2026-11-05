from fastapi.testclient import TestClient

from api.main import app
from engine.storage import insert_alert, record_message


def test_appareils_avec_score_de_risque():
    record_message("esp32-sec-01", "pir", 1, "bool")
    insert_alert("esp32-sec-01", "x", severity="high", sensor="pir", kind="anomaly")
    with TestClient(app) as client:
        devices = client.get("/api/devices").json()
        assert devices[0]["device_id"] == "esp32-sec-01" and devices[0]["risk"] == 40
        r = client.get("/api/devices/esp32-sec-01/risk").json()
        assert r["level"] == "à surveiller" and r["causes"][0]["sensor"] == "pir"
        assert client.get("/api/devices/inconnu/risk").status_code == 404


def test_commandes_limitees_aux_actionneurs_connus(monkeypatch):
    from api.routes import commands
    sent = []
    monkeypatch.setattr(commands, "_publish", lambda topic, payload: sent.append((topic, payload)))
    with TestClient(app) as client:
        assert "esp32-cmf-01" in client.get("/api/commands").json()["actuators"]
        r = client.post("/api/commands", json={"device_id": "esp32-cmf-01", "actuator": "relay", "value": "on"})
        assert r.status_code == 200 and sent == [("home/esp32-cmf-01/cmd/relay", "on")]
        assert client.post("/api/commands", json={"device_id": "esp32-cmf-01", "actuator": "relay",
                                                  "value": "rm -rf"}).status_code == 422
        assert client.post("/api/commands", json={"device_id": "x", "actuator": "relay",
                                                  "value": "on"}).status_code == 404


def test_alertes_d_un_episode():
    a = insert_alert("d", "x", severity="high", ts="2026-01-01T00:00:00+00:00", sensor="t", kind="anomaly")
    insert_alert("d", "x", severity="high", ts="2026-01-01T00:00:05+00:00", sensor="t", kind="anomaly")
    with TestClient(app) as client:
        rows = client.get(f"/api/alerts?episode_id={a['episode_id']}").json()
        assert len(rows) == 2 and rows[0]["ts"] < rows[1]["ts"]


def test_acquittement_d_un_episode():
    a = insert_alert("d", "x", severity="high", ts="2026-01-01T00:00:00+00:00", sensor="t", kind="anomaly")
    ep = a["episode_id"]
    with TestClient(app) as client:
        assert client.get("/api/episodes").json()[0]["acknowledged"] == 0
        r = client.post(f"/api/episodes/{ep}/ack", json={"note": "vérifié, rien à signaler"})
        assert r.status_code == 200 and r.json()["acknowledged"] == 1
        assert r.json()["ack_note"] == "vérifié, rien à signaler" and r.json()["ack_ts"]
        # dé-acquittement
        r = client.post(f"/api/episodes/{ep}/ack", json={"acknowledged": False})
        assert r.status_code == 200 and r.json()["acknowledged"] == 0 and r.json()["ack_ts"] is None
        assert client.post("/api/episodes/999999/ack").status_code == 404


def test_dernier_badge_refuse():
    from engine import ingest
    ingest.handle_telemetry({"device_id": "esp32-sec-01", "sensor": "rfid", "value": 0, "unit": "bool",
                             "ts": "2026-01-01T09:00:00+00:00", "meta": {"uid": "29 2F 3A 03"}})
    with TestClient(app) as client:
        r = client.get("/api/badges/last-refused").json()
        assert r["uid"] == "29 2F 3A 03" and r["device_id"] == "esp32-sec-01"


def test_journal_des_acces_avec_photo():
    import base64
    from datetime import datetime, timedelta, timezone
    from api.routes import camera
    from engine.storage import insert_access
    now = datetime.now(timezone.utc)
    jpeg = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8photo\xff\xd9").decode()
    camera._frames.append((now.timestamp(), jpeg))
    ok = insert_access("esp32-sec-01", "29 2F 3A 03", True, now.isoformat())
    # badge trop ancien pour le tampon d'images : marqué « sans photo »
    old = insert_access("esp32-sec-01", "DE AD BE EF", False, (now - timedelta(minutes=5)).isoformat())
    camera._process_accesses(0)
    with TestClient(app) as client:
        log = {r["id"]: r for r in client.get("/api/badges/access").json()}
        assert log[ok]["granted"] is True and log[ok]["has_capture"] is True
        assert log[old]["granted"] is False and log[old]["has_capture"] is False
        r = client.get(f"/api/badges/access/{ok}/capture")
        assert r.status_code == 200 and r.content == b"\xff\xd8photo\xff\xd9"
        assert client.get(f"/api/badges/access/{old}/capture").status_code == 404


def test_dernier_badge_refuse_absent():
    with TestClient(app) as client:
        assert client.get("/api/badges/last-refused").json() is None


def test_mode_simulation_signale():
    from engine import ingest
    from engine.storage import set_simulated
    m = ingest.parse_message("home/esp32-cmf-01/sim", b"1", "2026-01-01T00:00:00+00:00")
    assert m["simulated"] is True and m["device_id"] == "esp32-cmf-01"
    assert ingest.parse_message("home/esp32-cmf-01/sim", b"0", "2026-01-01T00:00:00+00:00")["simulated"] is False
    record_message("esp32-cmf-01", "temperature", 22.0, "C")
    set_simulated("esp32-cmf-01", True, "2026-01-01T00:00:00+00:00")
    with TestClient(app) as client:
        dev = [d for d in client.get("/api/devices").json() if d["device_id"] == "esp32-cmf-01"][0]
        assert dev["simulated"] is True
