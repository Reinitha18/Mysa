"""
API Mysa : expose au dashboard la liste des appareils, leur historique et les
alertes générées par le moteur. Voir chapitre 7.3 du mémoire pour la liste des
endpoints prévus.

Lancement : uvicorn api.main:app --reload

Si le dashboard a été compilé (cd dashboard && npm run build), l'API le sert aussi sur
/dashboard/ : un seul processus suffit pour la démonstration.
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from engine.storage import init_db, list_alerts, max_alert_id
from api import auth
from api.routes import badges, camera, devices, alerts, commands, episodes, notifications, streams

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIST = os.path.join(ROOT, "dashboard", "dist")
CAMERA_DIR = os.path.join(ROOT, "camera")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    captures = asyncio.create_task(camera.capture_loop())  # photo de chaque passage de badge
    yield
    captures.cancel()


app = FastAPI(
    title="Mysa API",
    description="API de supervision comportementale pour maison intelligente",
    version="0.2.0",
    lifespan=lifespan,
)

# Pendant le développement, le dashboard (port 5173 en Vite) tourne sur une
# autre origine que l'API (port 8000) : CORS doit l'autoriser explicitement.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# Mot de passe du dashboard (MYSA_DASHBOARD_PASSWORD) : protège /api/* et /ws/*, voir api/auth.py.
app.add_middleware(auth.AuthMiddleware)


@app.get("/")
def root():
    return {"service": "mysa-api", "status": "ok"}


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(episodes.router, prefix="/api/episodes", tags=["episodes"])
app.include_router(streams.router, prefix="/api/streams", tags=["streams"])
app.include_router(commands.router, prefix="/api/commands", tags=["commands"])
app.include_router(badges.router, prefix="/api/badges", tags=["badges"])
app.include_router(camera.router, prefix="/ws/camera", tags=["camera"])


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket, since_id: int | None = None):
    """Flux des nouvelles alertes en temps réel. Le moteur et l'API sont deux processus
    distincts : l'API consulte la base chaque seconde. Sans since_id, seules les alertes
    créées après la connexion sont envoyées."""
    await websocket.accept()
    last_id = since_id if since_id is not None else await asyncio.to_thread(max_alert_id)
    try:
        while True:
            for alert in await asyncio.to_thread(list_alerts, 100, last_id):
                await websocket.send_json(alert)
                last_id = alert["id"]
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass


if os.path.isdir(CAMERA_DIR):
    app.mount("/camera", StaticFiles(directory=CAMERA_DIR, html=True), name="camera")

if os.path.isdir(DASHBOARD_DIST):
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIST, html=True), name="dashboard")
