"""
Accès au dashboard. Sans protection, n'importe quel poste du réseau qui joint le port 8000 pourrait
ouvrir la serrure, désarmer l'alarme ou regarder la caméra.

Deux modes, qui peuvent coexister :
  - COMPTES (recommandé) : chaque occupant a un compte e-mail + mot de passe. Le mot de passe n'est jamais
    conservé : seule son empreinte salée (PBKDF2-SHA256, 600 000 itérations, sel aléatoire par compte) est
    stockée, impossible à inverser. Le premier compte se crée depuis le dashboard tant que rien n'est
    protégé ; ensuite, seul un utilisateur connecté peut en ajouter un autre.
  - MOT DE PASSE UNIQUE (historique) : MYSA_DASHBOARD_PASSWORD dans .env. Reste accepté sans e-mail, ce qui
    garde le lab d'attaque et les scripts existants fonctionnels.
Sans compte ni MYSA_DASHBOARD_PASSWORD, l'accès est libre (développement, tests, première utilisation).

Principe commun :
  - POST /api/auth/login pose un cookie de session signé (HMAC-SHA256, HttpOnly, SameSite=Strict, Secure en
    HTTPS), valable SESSION_S. Pour un compte, la signature dépend aussi de l'empreinte du mot de passe :
    changer de mot de passe déconnecte les autres appareils ;
  - toutes les routes /api/* et /ws/* (dont la caméra) exigent ce cookie, sauf status, login, logout, register ;
  - anti force brute : MAX_FAILURES échecs en FAILURE_WINDOW_S depuis une même adresse bloquent la
    connexion pendant LOCKOUT_S (même logique que le lecteur de badges de sec-01).
"""

import base64
import hashlib
import hmac
import os
import re
import sqlite3
import time
from http.cookies import SimpleCookie

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from engine.storage import (count_users, create_user, delete_user, get_secret, get_user, get_user_by_email,
                            list_users, set_user_password)

COOKIE = "mysa_session"
SESSION_S = 12 * 3600
MAX_FAILURES = 5
FAILURE_WINDOW_S = 300
LOCKOUT_S = 300
PBKDF2_ROUNDS = 600_000
MIN_PASSWORD = 8
PUBLIC_PATHS = {"/api/auth/status", "/api/auth/login", "/api/auth/logout", "/api/auth/register"}
PROTECTED_PREFIXES = ("/api/", "/ws/")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter()
_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}
_cache: dict = {"accounts": None, "checked": 0.0, "secret": None, "dummy": None}


# ---------- Mots de passe ----------
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, rounds, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def _dummy_hash() -> str:
    """Empreinte factice : un e-mail inconnu coûte autant de temps qu'un mot de passe faux."""
    if _cache["dummy"] is None:
        _cache["dummy"] = hash_password("mysa-dummy")
    return _cache["dummy"]


# ---------- Mode mot de passe unique (historique) ----------
def password() -> str | None:
    value = os.getenv("MYSA_DASHBOARD_PASSWORD", "").strip()
    return value or None


def _key(pw: str) -> bytes:
    return hashlib.sha256(f"mysa-session:{pw}".encode()).digest()


def make_token(pw: str, now: float | None = None) -> str:
    expires = int((now or time.time()) + SESSION_S)
    sig = hmac.new(_key(pw), str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def valid_token(token: str | None, pw: str, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    expires, sig = token.split(".", 1)
    if not expires.isdigit() or int(expires) < (now or time.time()):
        return False
    expected = hmac.new(_key(pw), expires.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


# ---------- Sessions des comptes ----------
def _user_key() -> bytes:
    if _cache["secret"] is None:
        _cache["secret"] = hashlib.sha256(f"mysa-user-session:{get_secret()}".encode()).digest()
    return _cache["secret"]


def _sign(user: dict, payload: str) -> str:
    fingerprint = hashlib.sha256(user["password_hash"].encode()).hexdigest()[:16]
    return hmac.new(_user_key(), f"{payload}.{fingerprint}".encode(), hashlib.sha256).hexdigest()


def make_user_token(user: dict, now: float | None = None) -> str:
    payload = f"u{user['id']}.{int((now or time.time()) + SESSION_S)}"
    return f"{payload}.{_sign(user, payload)}"


def user_from_token(token: str | None, now: float | None = None) -> dict | None:
    parts = (token or "").split(".")
    if len(parts) != 3 or not parts[0].startswith("u") or not parts[0][1:].isdigit() or not parts[1].isdigit():
        return None
    if int(parts[1]) < (now or time.time()):
        return None
    user = get_user(int(parts[0][1:]))
    if user is None or not hmac.compare_digest(parts[2], _sign(user, f"{parts[0]}.{parts[1]}")):
        return None
    return {"id": user["id"], "email": user["email"]}


def accounts_exist() -> bool:
    now = time.monotonic()
    if _cache["accounts"] is None or now - _cache["checked"] > 5.0:
        _cache["accounts"], _cache["checked"] = count_users() > 0, now
    return _cache["accounts"]


def required() -> bool:
    return password() is not None or accounts_exist()


def session_of(token: str | None) -> dict | None:
    """{'kind': 'user', 'user': {...}} ou {'kind': 'legacy'} si la session est valide, sinon None."""
    if token and token.startswith("u"):
        user = user_from_token(token)
        return {"kind": "user", "user": user} if user else None
    pw = password()
    return {"kind": "legacy"} if pw and valid_token(token, pw) else None


def _cookie_from_scope(scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            jar = SimpleCookie()
            jar.load(value.decode("latin-1"))
            if COOKIE in jar:
                return jar[COOKIE].value
    return None


class AuthMiddleware:
    """Middleware ASGI : couvre aussi les WebSockets, que le middleware HTTP de Starlette ignore."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if (path.startswith(PROTECTED_PREFIXES) and path.rstrip("/") not in PUBLIC_PATHS and required()
                    and session_of(_cookie_from_scope(scope)) is None):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 4401})  # refus avant acceptation
                    return
                response = JSONResponse({"detail": "Connexion requise"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class Login(BaseModel):
    email: str | None = None
    password: str


class Register(BaseModel):
    email: str
    password: str


class PasswordChange(BaseModel):
    current: str
    new: str


def _client(request: Request) -> str:
    return request.client.host if request.client else "?"


def _set_session(request: Request, response: Response, token: str):
    response.set_cookie(COOKIE, token, max_age=SESSION_S, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", path="/")


def _fail(who: str, now: float, detail: str):
    recent = [t for t in _failures.get(who, []) if now - t < FAILURE_WINDOW_S] + [now]
    _failures[who] = recent
    if len(recent) >= MAX_FAILURES:
        _locked_until[who] = now + LOCKOUT_S
        _failures.pop(who, None)
    raise HTTPException(status_code=401, detail=detail)


def _check_password_rules(email: str, pw: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise HTTPException(422, "Adresse e-mail invalide")
    if not MIN_PASSWORD <= len(pw) <= 128:
        raise HTTPException(422, f"Le mot de passe doit contenir au moins {MIN_PASSWORD} caractères")
    return email


@router.get("/status")
def auth_status(request: Request):
    """Le dashboard demande s'il doit afficher l'écran de connexion, et qui est connecté."""
    token = request.cookies.get(COOKIE)
    session = session_of(token)
    return {"required": required(), "authenticated": not required() or session is not None,
            "has_accounts": accounts_exist(), "legacy_password": password() is not None,
            "user": session["user"] if session and session["kind"] == "user" else None}


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    who, now = _client(request), time.time()
    if _locked_until.get(who, 0) > now:
        wait = int(_locked_until[who] - now)
        raise HTTPException(status_code=429, detail=f"Trop d'essais : réessayez dans {wait} s")
    email = (body.email or "").strip().lower()
    if email:
        user = get_user_by_email(email)
        ok = verify_password(body.password, user["password_hash"] if user else _dummy_hash())
        if not (user and ok):
            _fail(who, now, "E-mail ou mot de passe incorrect")
        _failures.pop(who, None)
        _set_session(request, response, make_user_token(user))
        return {"authenticated": True, "user": {"id": user["id"], "email": user["email"]}}
    pw = password()
    if pw is None:
        if accounts_exist():
            raise HTTPException(status_code=400, detail="Adresse e-mail requise")
        return {"authenticated": True}
    if not hmac.compare_digest(body.password.encode(), pw.encode()):
        _fail(who, now, "Mot de passe incorrect")
    _failures.pop(who, None)
    _set_session(request, response, make_token(pw))
    return {"authenticated": True}


@router.post("/register", status_code=201)
def register(body: Register, request: Request, response: Response):
    """Crée un compte. Libre tant que rien n'est protégé (premier compte, connexion automatique) ; ensuite
    réservé aux utilisateurs connectés (ajout d'un autre occupant)."""
    token = request.cookies.get(COOKIE)
    if required() and session_of(token) is None:
        raise HTTPException(status_code=401, detail="Connexion requise")
    email = _check_password_rules(body.email, body.password)
    try:
        user = create_user(email, hash_password(body.password))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cette adresse e-mail") from None
    _cache["accounts"] = None
    if not required() or session_of(token) is None:
        full = get_user(user["id"])
        _set_session(request, response, make_user_token(full))
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"authenticated": False}


@router.post("/password")
def change_password(body: PasswordChange, request: Request, response: Response):
    session = session_of(request.cookies.get(COOKIE))
    if not session or session["kind"] != "user":
        raise HTTPException(status_code=400, detail="Disponible pour les comptes avec adresse e-mail")
    user = get_user(session["user"]["id"])
    if not verify_password(body.current, user["password_hash"]):
        raise HTTPException(status_code=403, detail="Mot de passe actuel incorrect")
    _check_password_rules(user["email"], body.new)
    set_user_password(user["id"], hash_password(body.new))
    _set_session(request, response, make_user_token(get_user(user["id"])))  # les autres sessions sont fermées
    return {"changed": True}


@router.get("/users")
def get_users(request: Request):
    session = session_of(request.cookies.get(COOKIE))
    me = session["user"]["id"] if session and session["kind"] == "user" else None
    return [{**u, "current": u["id"] == me} for u in list_users()]


@router.delete("/users/{user_id}")
def remove_user(user_id: int, request: Request, response: Response):
    if count_users() <= 1:
        raise HTTPException(status_code=409, detail="C'est le dernier compte : le supprimer laisserait le dashboard sans protection")
    if not delete_user(user_id):
        raise HTTPException(status_code=404, detail="Compte inconnu")
    _cache["accounts"] = None
    session = session_of(request.cookies.get(COOKIE))
    if session and session["kind"] == "user" and session["user"]["id"] == user_id:
        response.delete_cookie(COOKIE, path="/")
    return {"deleted": user_id}


def reset():
    """Pour les tests : oublie les échecs, les blocages et les valeurs mises en cache."""
    _failures.clear()
    _locked_until.clear()
    _cache.update(accounts=None, checked=0.0, secret=None)
