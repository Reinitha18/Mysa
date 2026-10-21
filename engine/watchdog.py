"""
Chien de garde : détecte un appareil devenu silencieux.

Le moteur évalue un flux à l'arrivée d'un message ; si un appareil s'arrête, aucun
message n'arrive et aucune évaluation n'a lieu. Ce module compare l'âge du dernier
message de chaque flux à son rythme habituel (moyenne mobile des intervalles).

Seuil : max(SILENCE_MIN_S, SILENCE_FACTOR x intervalle habituel), et seulement
après MIN_MESSAGES messages (le rythme habituel n'est pas fiable avant).
Le silence est mesuré à l'horloge du serveur, par rapport à l'horodatage du dernier
message : les nœuds doivent donc laisser le moteur horodater les messages.
"""

import logging
import threading
from datetime import datetime, timezone

from engine.storage import _parse, insert_alert, list_streams, mark_silent

log = logging.getLogger("mysa.watchdog")

SILENCE_FACTOR = 10
SILENCE_MIN_S = 10.0
MIN_MESSAGES = 10


def check_silence(now: datetime | None = None) -> int:
    """Signale les flux silencieux ; retourne le nombre de nouveaux silences."""
    now = now or datetime.now(timezone.utc)
    count = 0
    for s in list_streams():
        if s["silent"] or not s["last_ts"] or s["ema_interval"] is None or s["message_count"] < MIN_MESSAGES:
            continue
        threshold = max(SILENCE_MIN_S, SILENCE_FACTOR * s["ema_interval"])
        age = (now - _parse(s["last_ts"])).total_seconds()
        if age > threshold:
            message = (f"Aucun message de {s['device_id']}/{s['sensor']} depuis {age:.0f} s "
                       f"(cadence habituelle ~{s['ema_interval']:.1f} s)")
            insert_alert(device_id=s["device_id"], message=message, severity="medium", ts=now.isoformat(),
                         sensor=s["sensor"], source="chien de garde", kind="silence")
            mark_silent(s["device_id"], s["sensor"])
            log.warning(message)
            count += 1
    return count


def start_watchdog(interval_s: float = 5.0) -> threading.Thread:
    def loop():
        while True:
            try:
                check_silence()
            except Exception:  # le chien de garde ne doit jamais arrêter le moteur
                log.exception("Erreur dans le chien de garde")
            threading.Event().wait(interval_s)
    thread = threading.Thread(target=loop, name="mysa-watchdog", daemon=True)
    thread.start()
    return thread
