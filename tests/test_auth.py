"""Mot de passe du dashboard (api/auth.py) et notifications de test (api/routes/notifications.py)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api import auth
from api.main import app
from engine import notify


def test_acces_libre_sans_mot_de_passe():
    with TestClient(app) as client:
        status = client.get("/api/auth/status").json()
        assert (status["required"], status["authenticated"], status["has_accounts"]) == (False, True, False)
        assert client.get("/api/devices").status_code == 200


def test_api_et_websockets_proteges(monkeypatch):
    monkeypatch.setenv("MYSA_DASHBOARD_PASSWORD", "s3cret")
    with TestClient(app) as client:
        status = client.get("/api/auth/status").json()
        assert (status["required"], status["authenticated"], status["legacy_password"]) == (True, False, True)
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


def test_comptes_email_mot_de_passe_hache():
    from engine.storage import get_user_by_email
    pw = "S3cret-mot-de-passe"
    with TestClient(app) as client:
        # Rien n'est protégé : le premier compte se crée librement et connecte automatiquement.
        assert client.post("/api/auth/register", json={"email": "Marie@Example.com", "password": "court"}).status_code == 422
        assert client.post("/api/auth/register", json={"email": "pas-un-mail", "password": pw}).status_code == 422
        r = client.post("/api/auth/register", json={"email": "Marie@Example.com", "password": pw})
        assert r.status_code == 201 and r.json()["email"] == "marie@example.com"
        status = client.get("/api/auth/status").json()
        assert status["required"] and status["authenticated"] and status["user"]["email"] == "marie@example.com"
        # Le mot de passe n'est jamais stocké en clair : seulement une empreinte salée.
        stored = get_user_by_email("marie@example.com")["password_hash"]
        assert stored.startswith("pbkdf2_sha256$") and pw not in stored
        # Désormais l'API est protégée ; sans session, on ne peut ni lire ni créer un compte.
        anonyme = TestClient(app)
        assert anonyme.get("/api/devices").status_code == 401
        assert anonyme.post("/api/auth/register", json={"email": "intrus@example.com", "password": pw}).status_code == 401
        assert anonyme.post("/api/auth/login", json={"email": "marie@example.com", "password": "faux-mot-de-passe"}).status_code == 401
        assert anonyme.post("/api/auth/login", json={"password": pw}).status_code == 400  # e-mail requis
        assert anonyme.post("/api/auth/login", json={"email": "MARIE@example.com", "password": pw}).status_code == 200
        assert anonyme.get("/api/devices").status_code == 200
        # Un utilisateur connecté ajoute un autre occupant ; l'e-mail est unique.
        assert client.post("/api/auth/register", json={"email": "paul@example.com", "password": pw + "2"}).status_code == 201
        assert client.post("/api/auth/register", json={"email": "paul@example.com", "password": pw + "3"}).status_code == 409
        users = client.get("/api/auth/users").json()
        assert [u["email"] for u in users] == ["marie@example.com", "paul@example.com"] and users[0]["current"] and "password_hash" not in users[0]
        # Changement de mot de passe : l'ancien ne marche plus, l'autre session est fermée.
        assert client.post("/api/auth/password", json={"current": "faux", "new": "nouveau-mdp-123"}).status_code == 403
        assert client.post("/api/auth/password", json={"current": pw, "new": "nouveau-mdp-123"}).status_code == 200
        assert client.get("/api/devices").status_code == 200           # cette session est renouvelée
        assert anonyme.get("/api/devices").status_code == 401           # l'autre est fermée
        assert TestClient(app).post("/api/auth/login", json={"email": "marie@example.com", "password": pw}).status_code == 401
        # On ne supprime pas le dernier compte (le dashboard resterait ouvert à tous).
        paul = next(u for u in users if u["email"] == "paul@example.com")
        assert client.delete(f"/api/auth/users/{paul['id']}").status_code == 200
        assert client.delete(f"/api/auth/users/{users[0]['id']}").status_code == 409


def test_mot_de_passe_unique_historique_reste_accepte_avec_des_comptes(monkeypatch):
    monkeypatch.setenv("MYSA_DASHBOARD_PASSWORD", "s3cret")
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"password": "s3cret"}).status_code == 200  # le lab d'attaque
        assert client.post("/api/auth/register", json={"email": "marie@example.com", "password": "S3cret-mot-de-passe"}).status_code == 201
        assert TestClient(app).get("/api/devices").status_code == 401
        assert client.get("/api/devices").status_code == 200
