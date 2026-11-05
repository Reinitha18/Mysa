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

# Hook facultatif appelé après chaque alerte enregistrée (notifications). Le moteur l'installe au
# démarrage (engine.ingest) ; sans hook (tests, rejeu hors ligne), insert_alert n'a aucun effet de
# bord. Le stockage ne dépend ainsi d'aucun module de plus haut niveau.
_alert_hook = None


def set_alert_hook(fn):
    """Installe (ou retire avec None) la fonction appelée après chaque insert_alert."""
    global _alert_hook
    _alert_hook = fn


def _fire_alert_hook(alert: dict):
    if _alert_hook is None:
        return
    try:
        _alert_hook(alert)
    except Exception:  # une notification ne doit jamais faire échouer l'enregistrement d'une alerte
        pass

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

-- Présence des nœuds (Last Will MQTT : home/<id>/status = online | offline)
CREATE TABLE IF NOT EXISTS presence (
    device_id TEXT PRIMARY KEY,
    online INTEGER NOT NULL,
    ts TEXT NOT NULL
);

-- Appareils en mode SIMULATION de repli (home/<id>/sim = 1 | 0), signalés dans le dashboard.
CREATE TABLE IF NOT EXISTS simulated (
    device_id TEXT PRIMARY KEY,
    simulated INTEGER NOT NULL,
    ts TEXT NOT NULL
);

-- Journal des accès : chaque badge présenté (accepté ou refusé), et la photo prise par la caméra
-- à ce moment-là (capture : nom du fichier, '' si aucune caméra, NULL tant que l'API n'a pas traité).
CREATE TABLE IF NOT EXISTS access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    uid TEXT,
    granted INTEGER NOT NULL,
    ts TEXT NOT NULL,
    capture TEXT
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device ON telemetry (device_id, ts);
CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts (device_id, ts);
CREATE INDEX IF NOT EXISTS idx_telemetry_stream ON telemetry (device_id, sensor, ts);
CREATE INDEX IF NOT EXISTS idx_telemetry_sensor ON telemetry (sensor, ts);
CREATE INDEX IF NOT EXISTS idx_episodes_end ON episodes (end_ts);
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

# Acquittement d'un épisode depuis le dashboard (gestion des alertes, chapitre 8).
EPISODE_EXTRA_COLUMNS = {
    "acknowledged": "INTEGER NOT NULL DEFAULT 0",
    "ack_ts": "TEXT",
    "ack_note": "TEXT",
}


def init_db():
    """Crée les tables si elles n'existent pas encore, et complète une base créée
    par une version précédente. À appeler au démarrage de l'API et du moteur."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        for table, columns in (("alerts", ALERT_EXTRA_COLUMNS), ("episodes", EPISODE_EXTRA_COLUMNS)):
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, decl in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


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
        result = {"alert_id": cur.lastrowid, "episode_id": episode_id, "new_episode": new_episode}
    _fire_alert_hook({"device_id": device_id, "message": message, "severity": severity, "ts": ts,
                      "sensor": sensor, "source": source, "kind": kind, **result})
    return result


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


def list_alerts(limit: int = 100, since_id: int | None = None, episode_id: int | None = None) -> list[dict]:
    """Alertes brutes (une par fenêtre signalée), les plus récentes en premier.
    Avec since_id : uniquement celles créées après cet identifiant, dans l'ordre.
    Avec episode_id : uniquement les alertes de cet épisode, dans l'ordre."""
    cols = "id, device_id, sensor, message, severity, ts, source, score, kind, episode_id"
    with get_connection() as conn:
        if episode_id is not None:
            rows = conn.execute(f"SELECT {cols} FROM alerts WHERE episode_id = ? ORDER BY id ASC LIMIT ?",
                                (episode_id, limit)).fetchall()
        elif since_id is not None:
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


def list_episodes_since(since_ts: str, device_id: str | None = None) -> list[dict]:
    """Épisodes dont la dernière alerte est postérieure à since_ts (score de risque)."""
    query = "SELECT * FROM episodes WHERE end_ts >= ?"
    params: list = [since_ts]
    if device_id:
        query += " AND device_id = ?"
        params.append(device_id)
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query + " ORDER BY end_ts DESC", params).fetchall()]


def get_episode(episode_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        return dict(row) if row else None


def set_episode_ack(episode_id: int, acknowledged: bool = True, note: str | None = None,
                    ts: str | None = None) -> dict | None:
    """Acquitte (ou dé-acquitte) un épisode. Retourne l'épisode mis à jour, ou None s'il
    n'existe pas. L'acquittement est un état de suivi : il ne modifie pas le score de risque,
    qui décroît de lui-même quand l'appareil redevient normal (engine/risk.py)."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM episodes WHERE id = ?", (episode_id,)).fetchone() is None:
            return None
        conn.execute("UPDATE episodes SET acknowledged = ?, ack_ts = ?, ack_note = ? WHERE id = ?",
                     (int(acknowledged), ts if acknowledged else None,
                      note if acknowledged else None, episode_id))
    return get_episode(episode_id)


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


# ---------- Présence des nœuds ----------
def set_presence(device_id: str, online: bool, ts: str) -> bool | None:
    """Enregistre l'état de présence d'un nœud. Retourne l'état précédent (None si inconnu)."""
    with get_connection() as conn:
        row = conn.execute("SELECT online FROM presence WHERE device_id = ?", (device_id,)).fetchone()
        conn.execute("INSERT INTO presence (device_id, online, ts) VALUES (?, ?, ?) "
                     "ON CONFLICT(device_id) DO UPDATE SET online = excluded.online, ts = excluded.ts",
                     (device_id, int(online), ts))
        return None if row is None else bool(row["online"])


def list_presence() -> dict[str, dict]:
    """{device_id: {"online": bool, "ts": ...}} pour les nœuds qui annoncent leur présence."""
    with get_connection() as conn:
        rows = conn.execute("SELECT device_id, online, ts FROM presence").fetchall()
        return {r["device_id"]: {"online": bool(r["online"]), "ts": r["ts"]} for r in rows}


def set_simulated(device_id: str, simulated: bool, ts: str):
    """Marque un appareil comme simulé (mode de repli) ou réel. Publié en MQTT retenu par le
    simulateur (home/<id>/sim) : le dashboard l'affiche clairement comme « Simulé »."""
    with get_connection() as conn:
        conn.execute("INSERT INTO simulated (device_id, simulated, ts) VALUES (?, ?, ?) "
                     "ON CONFLICT(device_id) DO UPDATE SET simulated = excluded.simulated, ts = excluded.ts",
                     (device_id, int(simulated), ts))


def list_simulated() -> dict[str, bool]:
    """{device_id: True} pour les appareils actuellement en mode simulation."""
    with get_connection() as conn:
        rows = conn.execute("SELECT device_id FROM simulated WHERE simulated = 1").fetchall()
        return {r["device_id"]: True for r in rows}


def last_refused_badge() -> dict | None:
    """UID du dernier badge refusé (pour l'enrôlement en un clic depuis le dashboard), lu dans le
    journal des accès. Retourne {"uid", "device_id", "ts"} ou None."""
    with get_connection() as conn:
        row = conn.execute("SELECT uid, device_id, ts FROM access_log WHERE granted = 0 AND uid IS NOT NULL "
                           "ORDER BY ts DESC, id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


# ---------- Journal des accès (badges) ----------
def insert_access(device_id: str, uid: str | None, granted: bool, ts: str) -> int:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO access_log (device_id, uid, granted, ts) VALUES (?, ?, ?, ?)",
                           (device_id, uid, int(granted), ts))
        return cur.lastrowid


def list_access(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM access_log ORDER BY ts DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_access(access_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM access_log WHERE id = ?", (access_id,)).fetchone()
        return dict(row) if row else None


def access_without_capture(after_id: int) -> list[dict]:
    """Accès pas encore traités par la caméra (capture NULL), d'identifiant > after_id."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM access_log WHERE id > ? AND capture IS NULL ORDER BY id",
                            (after_id,)).fetchall()
        return [dict(r) for r in rows]


def max_access_id() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM access_log").fetchone()["m"]


def set_access_capture(access_id: int, capture: str):
    with get_connection() as conn:
        conn.execute("UPDATE access_log SET capture = ? WHERE id = ?", (capture, access_id))


def recent_values(device_id: str, sensor: str, since_ts: str) -> list[dict]:
    """Messages d'un flux postérieurs à since_ts, du plus ancien au plus récent (règles)."""
    with get_connection() as conn:
        rows = conn.execute("SELECT value, ts FROM telemetry WHERE device_id = ? AND sensor = ? AND ts >= ? "
                            "ORDER BY ts ASC", (device_id, sensor, since_ts)).fetchall()
        return [dict(r) for r in rows]


def latest_value(sensor: str, device_id: str | None = None) -> dict | None:
    """Dernier message d'un capteur (le plus récent), dans toute la maison ou pour un appareil
    donné. Sert à la corrélation pour connaître l'état courant (alarme armée, par ex.)."""
    query = "SELECT device_id, sensor, value, ts FROM telemetry WHERE sensor = ?"
    params: list = [sensor]
    if device_id:
        query += " AND device_id = ?"
        params.append(device_id)
    query += " ORDER BY ts DESC, id DESC LIMIT 1"
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def recent_messages(sensors, since_ts: str, device_id: str | None = None) -> list[dict]:
    """Messages de plusieurs capteurs depuis since_ts (toute la maison par défaut), du plus
    ancien au plus récent. Sert à la corrélation entre capteurs (engine/correlation.py)."""
    sensors = list(sensors)
    if not sensors:
        return []
    placeholders = ",".join("?" for _ in sensors)
    query = (f"SELECT device_id, sensor, value, ts FROM telemetry "
             f"WHERE sensor IN ({placeholders}) AND ts >= ?")
    params: list = [*sensors, since_ts]
    if device_id:
        query += " AND device_id = ?"
        params.append(device_id)
    query += " ORDER BY ts ASC"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
