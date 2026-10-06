"""
API Mysa : expose au dashboard la liste des appareils, leur historique et les
alertes générées par le moteur. Voir chapitre 7.3 du mémoire pour la liste des
endpoints prévus.

Lancement : uvicorn api.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.storage import init_db
from api.routes import devices, alerts

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
