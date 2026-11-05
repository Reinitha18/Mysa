"""
Accès au dashboard par mot de passe. Sans lui, n'importe quel poste du réseau qui joint le port 8000
pourrait ouvrir la serrure, désarmer l'alarme ou regarder la caméra.

Principe :
  - MYSA_DASHBOARD_PASSWORD (.env) active la protection ; vide = accès libre (développement, tests) ;
  - POST /api/auth/login vérifie le mot de passe (comparaison à temps constant) et pose un cookie de
    session signé (HMAC-SHA256, HttpOnly, SameSite=Strict, Secure en HTTPS), valable SESSION_S ;
  - toutes les routes /api/* et /ws/* (dont la caméra) exigent ce cookie, sauf /api/auth/* ;
  - anti force brute : MAX_FAILURES échecs en FAILURE_WINDOW_S depuis une même adresse bloquent la
    connexion pendant LOCKOUT_S (même logique que le lecteur de badges de sec-01).

La clé de signature dérive du mot de passe : changer le mot de passe invalide toutes les sessions,
et un redémarrage du hub ne déconnecte personne.
"""

import hashlib
import hmac
import os
import time
from http.cookies import SimpleCookie

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

COOKIE = "mysa_session"
SESSION_S = 12 * 3600
MAX_FAILURES = 5
FAILURE_WINDOW_S = 300
LOCKOUT_S = 300
PUBLIC_PREFIXES = ("/api/auth/",)
PROTECTED_PREFIXES = ("/api/", "/ws/")

router = APIRouter()
_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


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
            pw = password()
            if (pw and path.startswith(PROTECTED_PREFIXES) and not path.startswith(PUBLIC_PREFIXES)
                    and not valid_token(_cookie_from_scope(scope), pw)):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 4401})  # refus avant acceptation
                    return
                response = JSONResponse({"detail": "Connexion requise"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class Login(BaseModel):
    password: str


def _client(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.get("/status")
def auth_status(request: Request):
    """Le dashboard demande s'il doit afficher l'écran de connexion."""
    pw = password()
    return {"required": pw is not None,
            "authenticated": pw is None or valid_token(request.cookies.get(COOKIE), pw)}


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    pw = password()
    if pw is None:
        return {"authenticated": True}
    who, now = _client(request), time.time()
    if _locked_until.get(who, 0) > now:
        wait = int(_locked_until[who] - now)
        raise HTTPException(status_code=429, detail=f"Trop d'essais : réessayez dans {wait} s")
    if not hmac.compare_digest(body.password.encode(), pw.encode()):
        recent = [t for t in _failures.get(who, []) if now - t < FAILURE_WINDOW_S] + [now]
        _failures[who] = recent
        if len(recent) >= MAX_FAILURES:
            _locked_until[who] = now + LOCKOUT_S
            _failures.pop(who, None)
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    _failures.pop(who, None)
    response.set_cookie(COOKIE, make_token(pw), max_age=SESSION_S, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", path="/")
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"authenticated": False}


def reset():
    """Pour les tests : oublie les échecs et blocages."""
    _failures.clear()
    _locked_until.clear()
