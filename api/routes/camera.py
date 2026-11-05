"""
Caméra du téléphone (mémoire, chapitre 8). Le téléphone ouvre camera/index.html dans Chrome et,
pour chaque image, envoie au hub par WebSocket :
  - un JPEG (affichage temps réel sur le dashboard) ;
  - une vignette en niveaux de gris réduite (détection de mouvement sur le hub, engine/vision.py).

Le hub RELAIE les images vers les dashboards connectés et, à la détection d'un mouvement, publie
home/<cam>/motion en MQTT avec un compte DÉDIÉ (mysa-cam) que l'ACL du broker restreint à
home/<cam>/#. Le moteur ingère ce topic comme n'importe quel capteur de mouvement.

Seule exception à « aucun enregistrement » : la photo d'un passage de badge. Le hub garde les
images des dernières secondes en mémoire ; quand le moteur consigne un badge (accepté ou refusé)
dans le journal des accès, l'API enregistre l'image la plus proche de cet instant
(capture_loop, data/captures/), pour une vérification ultérieure depuis le dashboard.

Trois points d'accès :
  WS /ws/camera/publish  : le téléphone pousse ses images.
  WS /ws/camera/view     : un dashboard reçoit le flux (dernière image d'abord).
  GET /ws/camera/status  : état (téléphone connecté ? nombre de spectateurs ?).

Flux non chiffré au niveau applicatif : il transite dans le VLAN du hub, et l'accès à la caméra dans
Chrome impose déjà HTTPS (certificat de la CA Mysa, voir docs/https.md).
"""

import asyncio
import base64
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone

import numpy as np
import paho.mqtt.publish as publish
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from engine.storage import DB_PATH, access_without_capture, max_access_id, set_access_capture
from engine.vision import MotionDetector

log = logging.getLogger("mysa.camera")
router = APIRouter()

CAM_DEVICE = os.getenv("MYSA_CAM_DEVICE", "cam-01")

_viewers: set[WebSocket] = set()
_latest: dict | None = None
_phone_connected = False

BUFFER_S = 15            # images gardées en mémoire (secondes), pour retrouver l'instant d'un badge
CAPTURE_MAX_GAP_S = 5    # écart maximal entre le badge et l'image retenue
CAPTURE_KEEP = 500       # photos conservées sur disque (les plus anciennes sont supprimées)
CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "captures")
_frames: deque = deque()  # (horodatage epoch, jpeg en data URL)


def publish_motion(value: int, ts: str):
    """Publie home/<cam>/motion avec le compte MQTT dédié de la caméra."""
    payload = json.dumps({"device_id": CAM_DEVICE, "sensor": "motion", "value": value,
                          "unit": "bool", "ts": ts})
    auth = None
    if os.getenv("MYSA_CAM_USER"):
        auth = {"username": os.getenv("MYSA_CAM_USER"), "password": os.getenv("MYSA_CAM_PASSWORD")}
    tls = {"ca_certs": os.getenv("MQTT_CA_CERT") or None} if os.getenv("MQTT_USE_TLS", "true").lower() == "true" else None
    publish.single(f"home/{CAM_DEVICE}/motion", payload, qos=1, hostname=os.getenv("MQTT_HOST", "localhost"),
                   port=int(os.getenv("MQTT_PORT", "8883")), client_id="mysa-cam", auth=auth, tls=tls)


async def _fanout(payload: dict):
    """Relaie une image aux dashboards connectés ; retire ceux qui ont coupé."""
    for ws in list(_viewers):
        try:
            await ws.send_json(payload)
        except Exception:
            _viewers.discard(ws)


def _epoch(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def _remember(jpeg: str | None):
    """Ajoute l'image au tampon des BUFFER_S dernières secondes (horloge du hub)."""
    if not jpeg:
        return
    now = datetime.now(timezone.utc).timestamp()
    _frames.append((now, jpeg))
    while _frames and now - _frames[0][0] > BUFFER_S:
        _frames.popleft()


def _frame_near(ts_s: float) -> str | None:
    """Image du tampon la plus proche de l'instant ts_s, si elle est à moins de CAPTURE_MAX_GAP_S."""
    best = min(_frames, key=lambda f: abs(f[0] - ts_s), default=None)
    return best[1] if best and abs(best[0] - ts_s) <= CAPTURE_MAX_GAP_S else None


def _save_capture(access: dict, jpeg: str) -> str:
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    stamp = datetime.fromtimestamp(_epoch(access["ts"]), timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}_{access['id']}_{'accepte' if access['granted'] else 'refuse'}.jpg"
    with open(os.path.join(CAPTURE_DIR, name), "wb") as f:
        f.write(base64.b64decode(jpeg.split(",", 1)[-1]))
    files = sorted(os.listdir(CAPTURE_DIR))
    for old in files[:-CAPTURE_KEEP]:
        os.remove(os.path.join(CAPTURE_DIR, old))
    return name


def _process_accesses(after_id: int) -> int:
    """Joint une photo aux nouveaux accès du journal. Un accès trop récent attend l'image qui suit
    le badge ; au-delà de CAPTURE_MAX_GAP_S sans image (caméra absente), il est marqué '' (aucune)."""
    now = datetime.now(timezone.utc).timestamp()
    for access in access_without_capture(after_id):
        ts_s = _epoch(access["ts"])
        jpeg = _frame_near(ts_s)
        if jpeg is None and now - ts_s < CAPTURE_MAX_GAP_S:
            break  # on réessaiera à la prochaine passe, dans l'ordre
        set_access_capture(access["id"], _save_capture(access, jpeg) if jpeg else "")
        after_id = access["id"]
    return after_id


async def capture_loop():
    """Tâche de fond de l'API (lancée au démarrage) : surveille le journal des accès."""
    after_id = await asyncio.to_thread(max_access_id)  # pas de rattrapage des accès antérieurs
    while True:
        try:
            after_id = await asyncio.to_thread(_process_accesses, after_id)
        except Exception as err:  # une photo ratée ne doit pas arrêter la surveillance
            log.warning("Capture d'accès impossible : %s", err)
        await asyncio.sleep(1.0)


async def _handle_frame(frame: dict, detector: MotionDetector):
    global _latest
    _latest = {"ts": frame.get("ts"), "jpeg": frame.get("jpeg")}
    _remember(_latest["jpeg"])
    await _fanout(_latest)

    gray = frame.get("gray")
    if not gray:
        return
    event = detector.update(np.asarray(gray, dtype=np.int16), asyncio.get_running_loop().time())
    if event is None:
        return
    value = 1 if event == "start" else 0
    ts = datetime.now(timezone.utc).isoformat()
    try:  # la publication MQTT ne doit pas interrompre le relais vidéo
        await asyncio.to_thread(publish_motion, value, ts)
        log.info("Caméra %s : mouvement %s -> home/%s/motion=%d", CAM_DEVICE,
                 "détecté" if value else "terminé", CAM_DEVICE, value)
    except Exception as err:
        log.warning("Publication du mouvement impossible : %s", err)


@router.websocket("/publish")
async def camera_publish(ws: WebSocket):
    """Le téléphone pousse ses images ici."""
    global _phone_connected
    await ws.accept()
    _phone_connected = True
    detector = MotionDetector()
    log.info("Caméra %s : téléphone connecté", CAM_DEVICE)
    try:
        while True:
            await _handle_frame(await ws.receive_json(), detector)
    except WebSocketDisconnect:
        pass
    finally:
        _phone_connected = False
        log.info("Caméra %s : téléphone déconnecté", CAM_DEVICE)


@router.websocket("/view")
async def camera_view(ws: WebSocket):
    """Un dashboard reçoit le flux en direct (dernière image connue d'abord)."""
    await ws.accept()
    _viewers.add(ws)
    try:
        if _latest:
            await ws.send_json(_latest)
        while True:
            await ws.receive_text()  # le spectateur n'envoie rien ; on attend la déconnexion
    except WebSocketDisconnect:
        pass
    finally:
        _viewers.discard(ws)


@router.get("/status")
def camera_status():
    return {"device_id": CAM_DEVICE, "phone_connected": _phone_connected, "viewers": len(_viewers)}
