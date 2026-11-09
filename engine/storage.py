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
import secrets
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

-- Badges autorisés connus du hub. Le nœud sec-01 ne publie que leur NOMBRE (capteur « badges »), pas
-- leurs UID : le hub tient donc un registre des badges ajoutés ou retirés depuis le dashboard
-- (removed_ts renseigné = retiré), complété à la lecture par les badges déjà acceptés au lecteur.
CREATE TABLE IF NOT EXISTS badge_registry (
    uid TEXT PRIMARY KEY,
    added_ts TEXT,
    removed_ts TEXT
);

-- Journal des campagnes de validation (lab d'attaque, scénarios TI-01 à TI-05) : une campagne,
-- puis un résultat par scénario. status : blocked | detected | undetected | not_run.
CREATE TABLE IF NOT EXISTS attack_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_ts TEXT NOT NULL,
    finished_ts TEXT NOT NULL,
    target TEXT
);
CREATE TABLE IF NOT EXISTS attack_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    ti TEXT NOT NULL,
    name TEXT NOT NULL,
    before TEXT,
    status TEXT NOT NULL,
    delay_s REAL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_attack_results_run ON attack_results (run_id);

-- Comptes du dashboard (connexion par e-mail). Le mot de passe n'est jamais conservé : seulement son
-- empreinte salée (PBKDF2-SHA256, voir api/auth.py), impossible à inverser.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_ts TEXT NOT NULL
);
-- Réglages internes (clé de signature des sessions, générée au premier démarrage).
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Gestion de la maison : maisons, puis nom / type / maison de chaque appareil et libellé de chaque capteur.
-- Un appareil sans fiche (house_id NULL) appartient à la première maison.
CREATE TABLE IF NOT EXISTS houses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    created_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device_meta (
    device_id TEXT PRIMARY KEY,
    house_id INTEGER,
    name TEXT,
    kind TEXT,
    created_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sensor_meta (
    device_id TEXT NOT NULL,
    sensor TEXT NOT NULL,
    label TEXT,
    unit TEXT,
    PRIMARY KEY (device_id, sensor)
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
        conn.execute("INSERT INTO houses (name, created_ts) SELECT 'Ma maison', ? "
                     "WHERE NOT EXISTS (SELECT 1 FROM houses)", (datetime.now(timezone.utc).isoformat(),))
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


# ---------- Badges autorisés (registre du hub) ----------
def normalize_uid(uid: str) -> str:
    """UID RFID en majuscules, séparés par un seul espace (« 29 2F 3A 03 »)."""
    return " ".join(uid.upper().split())


def registry_add_badge(uid: str, ts: str | None = None):
    """Badge autorisé depuis le dashboard (commande badge_add) : (ré)active son entrée."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("INSERT INTO badge_registry (uid, added_ts) VALUES (?, ?) "
                     "ON CONFLICT(uid) DO UPDATE SET added_ts = excluded.added_ts, removed_ts = NULL",
                     (normalize_uid(uid), ts))


def registry_remove_badge(uid: str, ts: str | None = None):
    """Badge retiré depuis le dashboard (commande badge_del). Une entrée est créée au besoin, pour
    qu'un badge connu seulement par le journal des accès disparaisse aussi de la liste."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("INSERT INTO badge_registry (uid, removed_ts) VALUES (?, ?) "
                     "ON CONFLICT(uid) DO UPDATE SET removed_ts = excluded.removed_ts",
                     (normalize_uid(uid), ts))


def list_authorized_badges() -> list[dict]:
    """Badges que le hub sait autorisés : ajoutés depuis le dashboard, ou déjà acceptés au lecteur.
    Un badge retiré reste exclu tant qu'il n'est pas de nouveau accepté après son retrait."""
    with get_connection() as conn:
        registry = {r["uid"]: dict(r) for r in conn.execute("SELECT * FROM badge_registry")}
        usage = {r["uid"]: dict(r) for r in conn.execute(
            "SELECT UPPER(TRIM(uid)) AS uid, MAX(ts) AS last_used, SUM(granted) AS granted, "
            "SUM(1 - granted) AS refused, MAX(CASE WHEN granted = 1 THEN ts END) AS last_granted "
            "FROM access_log WHERE uid IS NOT NULL AND TRIM(uid) != '' GROUP BY UPPER(TRIM(uid))")}
    badges = []
    for uid in set(registry) | {u for u, v in usage.items() if v["last_granted"]}:
        reg, use = registry.get(uid), usage.get(uid, {})
        removed, last_granted = reg and reg["removed_ts"], use.get("last_granted")
        if removed and not (last_granted and _parse(last_granted) > _parse(removed)):
            continue
        badges.append({"uid": uid, "source": "dashboard" if reg and reg["added_ts"] else "lecteur",
                       "added_ts": reg["added_ts"] if reg else None, "last_used": use.get("last_used"),
                       "granted": use.get("granted") or 0, "refused": use.get("refused") or 0})
    badges.sort(key=lambda b: (b["last_used"] is None, b["last_used"] and -_parse(b["last_used"]).timestamp(), b["uid"]))
    return badges


# ---------- Journal des campagnes d'attaque (validation) ----------
def insert_attack_run(started_ts: str, finished_ts: str, target: str | None, results: list[dict]) -> int:
    with get_connection() as conn:
        run_id = conn.execute("INSERT INTO attack_runs (started_ts, finished_ts, target) VALUES (?, ?, ?)",
                              (started_ts, finished_ts, target)).lastrowid
        conn.executemany(
            "INSERT INTO attack_results (run_id, ti, name, before, status, delay_s, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(run_id, r["ti"], r["name"], r.get("before"), r["status"], r.get("delay_s"), r.get("note"))
             for r in results])
    return run_id


def list_attack_runs(limit: int = 10) -> list[dict]:
    """Campagnes les plus récentes d'abord, chacune avec ses résultats (dans l'ordre d'exécution)."""
    with get_connection() as conn:
        runs = [dict(r) for r in conn.execute("SELECT * FROM attack_runs ORDER BY started_ts DESC, id DESC LIMIT ?",
                                              (limit,))]
        for run in runs:
            run["results"] = [dict(r) for r in conn.execute(
                "SELECT ti, name, before, status, delay_s, note FROM attack_results WHERE run_id = ? ORDER BY id",
                (run["id"],))]
    return runs


# ---------- Comptes ----------
def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_user(email: str, password_hash: str) -> dict:
    """Crée un compte (sqlite3.IntegrityError si l'e-mail existe déjà)."""
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO users (email, password_hash, created_ts) VALUES (?, ?, ?)",
                           (email, password_hash, _utcnow()))
        return {"id": cur.lastrowid, "email": email}


def get_user_by_email(email: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users() -> list[dict]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT id, email, created_ts FROM users ORDER BY id")]


def count_users() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def set_user_password(user_id: int, password_hash: str):
    with get_connection() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def delete_user(user_id: int) -> bool:
    with get_connection() as conn:
        return conn.execute("DELETE FROM users WHERE id = ?", (user_id,)).rowcount > 0


def get_app_setting(key: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_app_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def get_secret() -> str:
    """Clé de signature des sessions : tirée au hasard au premier appel, puis conservée en base."""
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('session_secret', ?)",
                     (secrets.token_hex(32),))
        return conn.execute("SELECT value FROM app_settings WHERE key = 'session_secret'").fetchone()[0]


# ---------- Maisons, appareils, capteurs (gestion) ----------
def _upsert(conn, table: str, keys: dict, fields: dict, on_insert: dict | None = None):
    """INSERT ... ON CONFLICT DO UPDATE : seuls les champs fournis sont modifiés. Les noms de colonnes
    viennent du code appelant (listes blanches), jamais de la requête."""
    cols = {**keys, **(on_insert or {}), **fields}
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)}) "
           f"ON CONFLICT({', '.join(keys)}) DO ")
    sql += ("UPDATE SET " + ", ".join(f"{c} = excluded.{c}" for c in fields)) if fields else "NOTHING"
    conn.execute(sql, list(cols.values()))


def list_houses() -> list[dict]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM houses ORDER BY id")]


def default_house_id() -> int | None:
    with get_connection() as conn:
        return conn.execute("SELECT MIN(id) FROM houses").fetchone()[0]


def get_house(house_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM houses WHERE id = ?", (house_id,)).fetchone()
        return dict(row) if row else None


def create_house(name: str, address: str | None = None) -> dict:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO houses (name, address, created_ts) VALUES (?, ?, ?)", (name, address, _utcnow()))
    return get_house(cur.lastrowid)


def update_house(house_id: int, fields: dict) -> dict | None:
    fields = {k: v for k, v in fields.items() if k in ("name", "address")}
    if fields:
        with get_connection() as conn:
            conn.execute(f"UPDATE houses SET {', '.join(f'{c} = ?' for c in fields)} WHERE id = ?",
                         [*fields.values(), house_id])
    return get_house(house_id)


def delete_house(house_id: int) -> bool:
    """Supprime la maison ; ses appareils ne sont pas supprimés, ils passent à la première maison."""
    with get_connection() as conn:
        conn.execute("UPDATE device_meta SET house_id = NULL WHERE house_id = ?", (house_id,))
        return conn.execute("DELETE FROM houses WHERE id = ?", (house_id,)).rowcount > 0


def list_device_meta() -> dict[str, dict]:
    with get_connection() as conn:
        return {r["device_id"]: dict(r) for r in conn.execute("SELECT * FROM device_meta")}


def upsert_device_meta(device_id: str, fields: dict):
    fields = {k: v for k, v in fields.items() if k in ("name", "kind", "house_id")}
    with get_connection() as conn:
        _upsert(conn, "device_meta", {"device_id": device_id}, fields, {"created_ts": _utcnow()})


def device_known(device_id: str) -> bool:
    """Appareil déclaré dans le dashboard, ou déjà vu par le moteur."""
    with get_connection() as conn:
        return bool(conn.execute("SELECT 1 FROM device_meta WHERE device_id = ? UNION ALL "
                                 "SELECT 1 FROM telemetry WHERE device_id = ? LIMIT 1", (device_id, device_id)).fetchone())


DEVICE_TABLES = ("telemetry", "alerts", "episodes", "streams", "presence", "simulated", "access_log",
                 "sensor_meta", "device_meta")


def delete_device(device_id: str) -> int:
    """Supprime l'appareil et tout son historique (mesures, alertes, épisodes, flux). Retourne le nombre
    de mesures effacées. S'il publie encore, le moteur le re-découvrira comme un nouvel appareil."""
    with get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM telemetry WHERE device_id = ?", (device_id,)).fetchone()[0]
        for table in DEVICE_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE device_id = ?", (device_id,))
    return n


def list_sensor_meta() -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    with get_connection() as conn:
        for r in conn.execute("SELECT * FROM sensor_meta"):
            out.setdefault(r["device_id"], {})[r["sensor"]] = {"label": r["label"], "unit": r["unit"]}
    return out


def upsert_sensor_meta(device_id: str, sensor: str, fields: dict):
    fields = {k: v for k, v in fields.items() if k in ("label", "unit")}
    with get_connection() as conn:
        _upsert(conn, "sensor_meta", {"device_id": device_id, "sensor": sensor}, fields)


def delete_sensor(device_id: str, sensor: str) -> int:
    """Supprime le capteur : sa fiche, son flux, ses mesures, ses alertes et ses épisodes."""
    with get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM telemetry WHERE device_id = ? AND sensor = ?", (device_id, sensor)).fetchone()[0]
        for table in ("telemetry", "alerts", "episodes", "streams", "sensor_meta"):
            conn.execute(f"DELETE FROM {table} WHERE device_id = ? AND sensor = ?", (device_id, sensor))
    return n
