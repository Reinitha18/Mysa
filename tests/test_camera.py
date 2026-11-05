"""Caméra du téléphone : relais temps réel (WebSocket) et publication du mouvement."""
import json

from fastapi.testclient import TestClient

from api.main import app
from api.routes import camera


def frame(jpeg, gray):
    return {"ts": "2026-01-01T00:00:00+00:00", "jpeg": jpeg, "gray": gray, "gw": 32, "gh": 24}


def test_publish_motion_topic_et_compte_dedie(monkeypatch):
    sent = {}
    monkeypatch.setattr(camera.publish, "single",
                        lambda topic, payload, **kw: sent.update(topic=topic, payload=payload, kw=kw))
    monkeypatch.setenv("MYSA_CAM_USER", "mysa-cam")
    monkeypatch.setenv("MYSA_CAM_PASSWORD", "secret")
    monkeypatch.setenv("MYSA_USE_TLS", "false")
    monkeypatch.setenv("MQTT_USE_TLS", "false")
    camera.publish_motion(1, "2026-01-01T00:00:00+00:00")
    assert sent["topic"] == "home/cam-01/motion"
    body = json.loads(sent["payload"])
    assert body["sensor"] == "motion" and body["value"] == 1 and body["device_id"] == "cam-01"
    assert sent["kw"]["client_id"] == "mysa-cam" and sent["kw"]["auth"]["username"] == "mysa-cam"


def test_relais_vers_le_dashboard_et_detection(monkeypatch):
    published = []
    monkeypatch.setattr(camera, "publish_motion", lambda v, ts: published.append(v))
    with TestClient(app) as client:
        with client.websocket_connect("/ws/camera/view") as viewer:
            with client.websocket_connect("/ws/camera/publish") as phone:
                phone.send_json(frame("img1", [0] * 768))
                assert viewer.receive_json()["jpeg"] == "img1"   # image relayée telle quelle
                phone.send_json(frame("img2", [0] * 768))        # warmup
                viewer.receive_json()
                phone.send_json(frame("img3", [255] * 768))      # changement franc -> mouvement
                viewer.receive_json()
    assert published and published[0] == 1  # motion=1 publié au front montant


def test_status_initial():
    with TestClient(app) as client:
        s = client.get("/ws/camera/status").json()
        assert s["device_id"] == "cam-01" and "phone_connected" in s and "viewers" in s
