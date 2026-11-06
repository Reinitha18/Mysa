from fastapi.testclient import TestClient

from api.main import app
from engine.storage import insert_access, insert_alert, record_message


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


def test_badges_autorises_registre_du_hub(monkeypatch):
    from api.routes import commands
    sent = []
    monkeypatch.setattr(commands, "_publish", lambda topic, payload: sent.append((topic, payload)))
    uids = lambda r: {b["uid"] for b in r["badges"]}
    with TestClient(app) as client:
        vide = client.get("/api/badges/authorized").json()
        assert vide["badges"] == [] and vide["node_count"] is None and vide["unknown_count"] is None
        # Le nœud annonce 2 badges ; le hub n'en connaît qu'un (déjà accepté au lecteur).
        record_message("esp32-sec-01", "badges", 2, "count")
        insert_access("esp32-sec-01", "29 2F 3A 03", True, "2020-01-01T00:00:00+00:00")
        insert_access("esp32-sec-01", "AA BB CC DD", False, "2020-01-01T00:01:00+00:00")  # refusé : pas autorisé
        r = client.get("/api/badges/authorized").json()
        assert r["node_count"] == 2 and r["known_count"] == 1 and r["unknown_count"] == 1
        assert uids(r) == {"29 2F 3A 03"} and r["badges"][0]["source"] == "lecteur"
        # Ajout depuis le dashboard : le registre suit la commande envoyée.
        cmd = {"device_id": "esp32-sec-01", "actuator": "badge_add", "value": "aa bb cc dd"}
        assert client.post("/api/commands", json=cmd).status_code == 200
        r = client.get("/api/badges/authorized").json()
        assert uids(r) == {"29 2F 3A 03", "AA BB CC DD"} and r["unknown_count"] == 0
        # Retrait : le badge disparaît de la liste.
        cmd = {"device_id": "esp32-sec-01", "actuator": "badge_del", "value": "29 2F 3A 03"}
        assert client.post("/api/commands", json=cmd).status_code == 200
        assert uids(client.get("/api/badges/authorized").json()) == {"AA BB CC DD"}
        assert sent[-1] == ("home/esp32-sec-01/cmd/badge_del", "29 2F 3A 03")
        # Un UID mal formé est refusé et ne touche pas le registre.
        bad = {"device_id": "esp32-sec-01", "actuator": "badge_del", "value": "pas un uid"}
        assert client.post("/api/commands", json=bad).status_code == 422


def test_journal_de_validation_des_campagnes():
    run = {"started_ts": "2026-11-05T10:00:00+00:00", "finished_ts": "2026-11-05T10:03:00Z", "target": "hub",
           "results": [{"ti": "TI-01", "name": "Écoute", "before": "Réussie", "status": "blocked", "note": "TLS"},
                       {"ti": "TI-04", "name": "Saturation", "status": "detected", "delay_s": 8.5, "note": "rythme"},
                       {"ti": "TI-05", "name": "Caméra", "status": "undetected"}]}
    # Épisode levé pendant la campagne, et un autre bien avant : seul le premier est associé.
    insert_alert("esp32-sec-01", "rafale", severity="high", sensor="pir", kind="anomaly", ts="2026-11-05T10:01:00+00:00")
    insert_alert("esp32-sec-01", "ancien", severity="low", sensor="pir", kind="anomaly", ts="2026-11-04T08:00:00+00:00")
    with TestClient(app) as client:
        assert client.get("/api/validation/runs").json() == []
        assert client.post("/api/validation/runs", json=run).status_code == 201
        # Charges utiles refusées : statut inconnu, dates inversées, aucun résultat.
        bad = {**run, "results": [{"ti": "TI-01", "name": "x", "status": "reussi"}]}
        assert client.post("/api/validation/runs", json=bad).status_code == 422
        assert client.post("/api/validation/runs", json={**run, "finished_ts": "2026-11-05T09:00:00Z"}).status_code == 422
        assert client.post("/api/validation/runs", json={**run, "results": []}).status_code == 422
        runs = client.get("/api/validation/runs").json()
        assert len(runs) == 1 and [r["ti"] for r in runs[0]["results"]] == ["TI-01", "TI-04", "TI-05"]
        assert runs[0]["summary"] == {"blocked": 1, "detected": 1, "undetected": 1, "not_run": 0}
        assert runs[0]["results"][1]["delay_s"] == 8.5
        assert [e["device_id"] for e in runs[0]["episodes"]] == ["esp32-sec-01"] and len(runs[0]["episodes"]) == 1
