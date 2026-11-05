"""Mot de passe du dashboard (api/auth.py) et notifications de test (api/routes/notifications.py)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api import auth
from api.main import app
from engine import notify


def test_acces_libre_sans_mot_de_passe():
    with TestClient(app) as client:
        assert client.get("/api/auth/status").json() == {"required": False, "authenticated": True}
        assert client.get("/api/devices").status_code == 200


def test_api_et_websockets_proteges(monkeypatch):
    monkeypatch.setenv("MYSA_DASHBOARD_PASSWORD", "s3cret")
    with TestClient(app) as client:
        assert client.get("/api/auth/status").json() == {"required": True, "authenticated": False}
        assert client.get("/api/devices").status_code == 401
        assert client.post("/api/commands", json={"device_id": "esp32-sec-01", "actuator": "lock",
                                                  "value": "open"}).status_code == 401
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/camera/view"):
                pass
        assert client.post("/api/auth/login", json={"password": "faux"}).status_code == 401
        assert client.post("/api/auth/login", json={"password": "s3cret"}).status_code == 200
        assert client.get("/api/auth/status").json()["authenticated"] is True
        assert client.get("/api/devices").status_code == 200
        with client.websocket_connect("/ws/camera/view"):
            pass
        client.post("/api/auth/logout")
        assert client.get("/api/devices").status_code == 401


def test_session_signee_et_expiree():
    token = auth.make_token("pw", now=1000)
    assert auth.valid_token(token, "pw", now=1001)
    assert not auth.valid_token(token, "autre", now=1001)                    # mot de passe changé
    assert not auth.valid_token(token, "pw", now=1000 + auth.SESSION_S + 1)  # expirée
    expires, sig = token.split(".")
    assert not auth.valid_token(f"{int(expires) + 3600}.{sig}", "pw", now=1001)  # prolongée à la main


def test_force_brute_bloquee(monkeypatch):
    monkeypatch.setenv("MYSA_DASHBOARD_PASSWORD", "s3cret")
    with TestClient(app) as client:
        for _ in range(auth.MAX_FAILURES):
            assert client.post("/api/auth/login", json={"password": "x"}).status_code == 401
        # Bloqué : même le bon mot de passe est refusé pendant LOCKOUT_S
        assert client.post("/api/auth/login", json={"password": "s3cret"}).status_code == 429


def test_notifications_etat_et_test(monkeypatch):
    for key in ("MYSA_SMTP_HOST", "MYSA_SMTP_USER", "MYSA_SMTP_PASSWORD", "MYSA_SMTP_TO",
                "MYSA_SMS_URL", "MYSA_SMS_TO", "MYSA_SMS_USER", "MYSA_SMS_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MYSA_SMS_URL", "http://192.168.20.50:8080/message")
    monkeypatch.setenv("MYSA_SMS_TO", "+261000000000")

    def boom(url, data=None, headers=None):
        raise OSError("réseau coupé")
    monkeypatch.setattr(notify, "_http", boom)
    with TestClient(app) as client:
        state = client.get("/api/notifications").json()
        assert state["channels"] == {"e-mail": False, "SMS": True}
        results = client.post("/api/notifications/test").json()["results"]
        assert results["e-mail"] == "non configuré"
        assert results["SMS"].startswith("échec") and "réseau coupé" in results["SMS"]
