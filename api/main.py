"""
API Mysa : expose au dashboard la liste des appareils, leur historique et les
alertes générées par le moteur. Voir chapitre 7.3 du mémoire pour la liste des
endpoints prévus.

Lancement : uvicorn api.main:app --reload
"""

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from engine.storage import init_db, list_alerts, max_alert_id
from api.routes import devices, alerts, episodes, streams

app = FastAPI(
    title="Mysa API",
    description="API de supervision comportementale pour maison intelligente",
    version="0.1.0",
)

# Pendant le développement, le dashboard (port 5173 en Vite) tourne sur une
# autre origine que l'API (port 8000) : CORS doit l'autoriser explicitement.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {"service": "mysa-api", "status": "ok"}


app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(episodes.router, prefix="/api/episodes", tags=["episodes"])
app.include_router(streams.router, prefix="/api/streams", tags=["streams"])


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
