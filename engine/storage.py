"""
Stockage local de la télémétrie et des alertes de Mysa.

On utilise SQLite plutôt qu'une base de données serveur : le prototype tourne sur
une seule VM, et SQLite évite d'avoir à installer et sécuriser un service
supplémentaire pour un projet de cette échelle (voir chapitre 6 du mémoire,
"étude et choix des outils").

Le moteur (engine/ingest.py) écrit dans cette base ; l'API (api/routes/*) y lit.
Les deux processus pointent vers le même fichier via la variable DB_PATH.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./mysa.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    sensor TEXT NOT NULL,
    value REAL,
    unit TEXT,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL,
    ts TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device ON telemetry (device_id, ts);
CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts (device_id, ts);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Crée les tables si elles n'existent pas encore. À appeler au démarrage
    de l'API et du moteur."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def insert_telemetry(device_id: str, sensor: str, value: float, unit: str, ts: str | None = None):
    ts = ts or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO telemetry (device_id, sensor, value, unit, ts) VALUES (?, ?, ?, ?, ?)",
            (device_id, sensor, value, unit, ts),
        )


def insert_alert(device_id: str, message: str, severity: str = "medium", ts: str | None = None):
    ts = ts or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO alerts (device_id, message, severity, ts) VALUES (?, ?, ?, ?)",
            (device_id, message, severity, ts),
        )


def list_devices() -> list[dict]:
    """Retourne chaque appareil vu au moins une fois, avec l'horodatage de son
    dernier message (utile pour le statut affiché sur le dashboard)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT device_id, MAX(ts) AS last_seen, COUNT(*) AS message_count
            FROM telemetry
            GROUP BY device_id
            ORDER BY last_seen DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_history(device_id: str, limit: int = 200) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT sensor, value, unit, ts FROM telemetry
            WHERE device_id = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (device_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def list_alerts(limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT device_id, message, severity, ts FROM alerts ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
