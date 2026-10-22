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

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    sensor TEXT,
    kind TEXT NOT NULL,
    source TEXT,
    severity TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    alert_count INTEGER NOT NULL DEFAULT 1,
    min_score REAL
);

CREATE TABLE IF NOT EXISTS streams (
    device_id TEXT NOT NULL,
    sensor TEXT NOT NULL,
    category TEXT,
    regime TEXT,
    ref_status TEXT,
    local_samples INTEGER NOT NULL DEFAULT 0,
    last_ts TEXT,
    ema_interval REAL,
    message_count INTEGER NOT NULL DEFAULT 0,
    silent INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (device_id, sensor)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device ON telemetry (device_id, ts);
CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts (device_id, ts);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL : le moteur écrit pendant que l'API lit, sans se bloquer. synchronous=NORMAL évite
    # une synchronisation disque à chaque écriture (coûteuse sous Windows) ; en cas de coupure
    # brutale, seules les toutes dernières mesures peuvent être perdues, jamais la base.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Colonnes ajoutées à la table alerts après la première version (migration douce).
ALERT_EXTRA_COLUMNS = {
    "sensor": "TEXT",
    "source": "TEXT",
    "score": "REAL",
    "kind": "TEXT DEFAULT 'anomaly'",
    "episode_id": "INTEGER",
}


def init_db():
    """Crée les tables si elles n'existent pas encore, et complète une base créée
    par une version précédente. À appeler au démarrage de l'API et du moteur."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(alerts)")}
        for column, decl in ALERT_EXTRA_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE alerts ADD COLUMN {column} {decl}")


def insert_telemetry(device_id: str, sensor: str, value: float, unit: str, ts: str | None = None):
    ts = ts or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO telemetry (device_id, sensor, value, unit, ts) VALUES (?, ?, ?, ?, ?)",
            (device_id, sensor, value, unit, ts),
        )
    return ts


# Deux alertes d'un même flux séparées de moins de EPISODE_GAP_S secondes (temps des
# messages) appartiennent au même épisode : une seule déviation, évaluée sur des
# fenêtres glissantes qui se chevauchent, produit sinon une grappe d'alertes.
EPISODE_GAP_S = 60.0


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def record_message(device_id: str, sensor: str, value, unit, ts: str | None = None) -> str:
    """Enregistre un message ET met à jour le registre du flux dans une seule transaction
    (une seule écriture disque par message). Retourne l'horodatage retenu."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("INSERT INTO telemetry (device_id, sensor, value, unit, ts) VALUES (?, ?, ?, ?, ?)",
                     (device_id, sensor, value, unit, ts))
        _touch_stream(conn, device_id, sensor, ts)
    return ts


def insert_alert(device_id: str, message: str, severity: str = "medium", ts: str | None = None,
                 sensor: str | None = None, source: str | None = None, score: float | None = None,
                 kind: str = "anomaly") -> dict:
    """Enregistre une alerte et la rattache à un épisode.

    Retourne {"alert_id", "episode_id", "new_episode"}. Les alertes de type
    "notice" (avis, par ex. référence rejetée) ne sont pas regroupées."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        episode_id, new_episode = None, True
        if kind != "notice" and sensor:
            last = conn.execute(
                "SELECT id, end_ts FROM episodes WHERE device_id = ? AND sensor = ? AND kind = ? "
                "ORDER BY end_ts DESC LIMIT 1", (device_id, sensor, kind)).fetchone()
            if last and 0 <= (_parse(ts) - _parse(last["end_ts"])).total_seconds() <= EPISODE_GAP_S:
                episode_id, new_episode = last["id"], False
                conn.execute(
                    "UPDATE episodes SET end_ts = ?, alert_count = alert_count + 1, "
                    "min_score = CASE WHEN ? IS NOT NULL AND (min_score IS NULL OR ? < min_score) "
                    "THEN ? ELSE min_score END WHERE id = ?", (ts, score, score, score, episode_id))
        if episode_id is None:
            cur = conn.execute(
                "INSERT INTO episodes (device_id, sensor, kind, source, severity, start_ts, end_ts, "
                "alert_count, min_score) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (device_id, sensor, kind, source, severity, ts, ts, score))
            episode_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO alerts (device_id, message, severity, ts, sensor, source, score, kind, episode_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (device_id, message, severity, ts, sensor, source, score, kind, episode_id))
        return {"alert_id": cur.lastrowid, "episode_id": episode_id, "new_episode": new_episode}


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


def get_history(device_id: str, limit: int = 200, sensor: str | None = None) -> list[dict]:
    """Derniers messages d'un appareil (les plus récents en premier), éventuellement
    restreints à un seul capteur."""
    query = "SELECT sensor, value, unit, ts FROM telemetry WHERE device_id = ?"
    params: list = [device_id]
    if sensor:
        query += " AND sensor = ?"
        params.append(sensor)
    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def list_alerts(limit: int = 100, since_id: int | None = None) -> list[dict]:
    """Alertes brutes (une par fenêtre signalée), les plus récentes en premier.
    Avec since_id : uniquement celles créées après cet identifiant, dans l'ordre."""
    cols = "id, device_id, sensor, message, severity, ts, source, score, kind, episode_id"
    with get_connection() as conn:
        if since_id is not None:
            rows = conn.execute(f"SELECT {cols} FROM alerts WHERE id > ? ORDER BY id ASC LIMIT ?",
                                (since_id, limit)).fetchall()
        else:
            rows = conn.execute(f"SELECT {cols} FROM alerts ORDER BY ts DESC, id DESC LIMIT ?",
                                (limit,)).fetchall()
        return [dict(row) for row in rows]


def list_episodes(limit: int = 100, device_id: str | None = None) -> list[dict]:
    """Épisodes d'alerte (regroupement des alertes d'un même flux), les plus récents en premier."""
    query = "SELECT * FROM episodes"
    params: list = []
    if device_id:
        query += " WHERE device_id = ?"
        params.append(device_id)
    query += " ORDER BY end_ts DESC, id DESC LIMIT ?"
    params.append(limit)
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


# ---------- Registre des flux (un flux = un appareil + un capteur) ----------
EMA_ALPHA = 0.2


def _touch_stream(conn, device_id: str, sensor: str, ts: str):
    row = conn.execute("SELECT last_ts, ema_interval FROM streams WHERE device_id = ? AND sensor = ?",
                       (device_id, sensor)).fetchone()
    if row is None:
        conn.execute("INSERT INTO streams (device_id, sensor, last_ts, message_count) VALUES (?, ?, ?, 1)",
                     (device_id, sensor, ts))
        return
    ema = row["ema_interval"]
    if row["last_ts"]:
        gap = max((_parse(ts) - _parse(row["last_ts"])).total_seconds(), 0.0)
        ema = gap if ema is None else (1 - EMA_ALPHA) * ema + EMA_ALPHA * gap
    conn.execute("UPDATE streams SET last_ts = ?, ema_interval = ?, message_count = message_count + 1, "
                 "silent = 0 WHERE device_id = ? AND sensor = ?", (ts, ema, device_id, sensor))


def touch_stream(device_id: str, sensor: str, ts: str):
    """Met à jour le dernier message vu, le rythme habituel (moyenne mobile des intervalles)
    et lève l'état « silencieux »."""
    with get_connection() as conn:
        _touch_stream(conn, device_id, sensor, ts)


def upsert_stream(device_id: str, sensor: str, **fields):
    """Met à jour l'état d'un flux (catégorie, régime, statut de la référence, échantillons locaux)."""
    allowed = {"category", "regime", "ref_status", "local_samples"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO streams (device_id, sensor) VALUES (?, ?)", (device_id, sensor))
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE streams SET {sets} WHERE device_id = ? AND sensor = ?",
                     [*fields.values(), device_id, sensor])


def list_streams() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM streams ORDER BY device_id, sensor").fetchall()
        return [dict(row) for row in rows]


def mark_silent(device_id: str, sensor: str):
    with get_connection() as conn:
        conn.execute("UPDATE streams SET silent = 1 WHERE device_id = ? AND sensor = ?", (device_id, sensor))


def max_alert_id() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM alerts").fetchone()
        return row["m"]
