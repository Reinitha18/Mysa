"""
Notifications gratuites (mémoire, chapitre 8). Deux canaux, chacun activé par des variables
d'environnement et simplement ignoré s'il n'est pas configuré :

  - e-mail : SMTP, par ex. Gmail avec un « mot de passe d'application » (gratuit) ;
  - SMS    : passerelle HTTP open source sur un téléphone Android (envoi avec la carte SIM).

Quoi notifier : les alertes CRITIQUES seulement, c'est-à-dire toute alerte de gravité « high »
(alarme, intrusion, lecteur de badges bloqué, surchauffe, valeurs hors contrat) et tout passage
d'un nœud hors ligne (Last Will : un nœud de sécurité coupé peut être un sabotage). Les alertes
moyennes et faibles restent consultables dans le dashboard.
Pour ne pas inonder, UNE SEULE notification par épisode : le moteur fournit le drapeau
new_episode (engine/storage.insert_alert).

Branchement : engine.ingest enregistre on_alert comme « hook » de storage.insert_alert
(storage.set_alert_hook). Le moteur appelle donc les notifications sans que le stockage ne
dépende de ce module, et le rejeu hors ligne (qui n'enregistre pas de hook) n'envoie rien.

Robustesse : chaque envoi est tenté dans un thread et protégé par try/except. Une latence ou une
panne d'un canal ne doit jamais ralentir ni arrêter l'ingestion MQTT. Aucune dépendance
supplémentaire : smtplib et urllib de la bibliothèque standard.

Guide de configuration (comptes, mot de passe d'application, application SMS) :
docs/notifications.md.
"""

import logging
import os
import smtplib
import threading
import urllib.parse
import urllib.request
from email.message import EmailMessage

log = logging.getLogger("mysa.notify")

HTTP_TIMEOUT_S = 10


def _env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def enabled() -> bool:
    return os.getenv("MYSA_NOTIFY", "1") == "1"


def should_notify(severity: str, kind: str, new_episode: bool) -> bool:
    """On notifie la première alerte d'un épisode critique : gravité « high » ou nœud hors ligne."""
    if not new_episode:
        return False
    return severity == "high" or kind == "offline"


def _format(device_id: str, message: str, severity: str, kind: str) -> tuple[str, str]:
    """(sujet court, corps) d'une notification, dans les mots de l'occupant."""
    if kind == "offline":
        head = "Mysa — nœud hors ligne"
    elif severity == "high":
        head = "Mysa — ALERTE"
    else:
        head = "Mysa — information"
    subject = f"{head} ({device_id})"
    return subject, message


# ---------------------------------------------------------------- canaux
def send_email(subject: str, body: str) -> bool:
    host, user, password = _env("MYSA_SMTP_HOST"), _env("MYSA_SMTP_USER"), _env("MYSA_SMTP_PASSWORD")
    recipients = _env("MYSA_SMTP_TO")
    if not (host and user and password and recipients):
        return False
    port = int(os.getenv("MYSA_SMTP_PORT", "587"))
    msg = EmailMessage()
    msg["From"] = _env("MYSA_SMTP_FROM") or user
    msg["To"] = recipients
    msg["Subject"] = subject
    msg.set_content(body)
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=HTTP_TIMEOUT_S) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=HTTP_TIMEOUT_S) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
    return True


def _http(url: str, data: bytes | None = None, headers: dict | None = None) -> None:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:  # nosec: URL de configuration, hub local
        resp.read()


def send_sms(text: str) -> bool:
    """Passerelle HTTP d'un téléphone Android (API locale de type android-sms-gateway, capcom6).
    POST JSON {"message", "phoneNumbers"} avec authentification basique. Voir docs/notifications.md."""
    url, to = _env("MYSA_SMS_URL"), _env("MYSA_SMS_TO")
    if not (url and to):
        return False
    import base64
    import json
    payload = json.dumps({"message": text, "phoneNumbers": [n.strip() for n in to.split(",")]}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    user, password = _env("MYSA_SMS_USER"), _env("MYSA_SMS_PASSWORD")
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    _http(url, data=payload, headers=headers)
    return True


CHANNELS = {"e-mail": lambda subj, body: send_email(subj, body),
            "SMS": lambda subj, body: send_sms(f"{subj}\n{body}")}


def configured() -> dict[str, bool]:
    """Canaux renseignés dans .env (sans rien envoyer) : affiché par le dashboard."""
    return {
        "e-mail": all(_env(k) for k in ("MYSA_SMTP_HOST", "MYSA_SMTP_USER", "MYSA_SMTP_PASSWORD", "MYSA_SMTP_TO")),
        "SMS": all(_env(k) for k in ("MYSA_SMS_URL", "MYSA_SMS_TO")),
    }


def send_test() -> dict[str, str]:
    """Notification de test sur chaque canal (bouton du dashboard), avec le résultat de chacun :
    « envoyé », « non configuré » ou « échec : <raison> »."""
    subject, body = "Mysa — test de notification", "Ceci est un test envoyé depuis le dashboard Mysa."
    result = {}
    for name, send in CHANNELS.items():
        try:
            result[name] = "envoyé" if send(subject, body) else "non configuré"
        except Exception as err:
            result[name] = f"échec : {err}"
    return result


def dispatch(device_id: str, message: str, severity: str, kind: str) -> list[str]:
    """Envoie la notification sur chaque canal configuré (synchrone). Retourne les canaux servis.
    Chaque canal est isolé : l'échec de l'un n'empêche pas les autres."""
    subject, body = _format(device_id, message, severity, kind)
    sent = []
    for name, send in CHANNELS.items():
        try:
            if send(subject, body):
                sent.append(name)
        except Exception as err:  # réseau, authentification, configuration : on journalise et on continue
            log.warning("Notification %s échouée : %s", name, err)
    if sent:
        log.info("Notification envoyée (%s) : %s", ", ".join(sent), subject)
    return sent


def on_alert(alert: dict) -> None:
    """Hook branché sur storage.insert_alert. Décide, puis envoie dans un thread (non bloquant)."""
    if not enabled():
        return
    if not should_notify(alert.get("severity", ""), alert.get("kind", ""), alert.get("new_episode", False)):
        return
    threading.Thread(target=dispatch, name="mysa-notify", daemon=True,
                     args=(alert.get("device_id", "?"), alert.get("message", ""),
                           alert.get("severity", ""), alert.get("kind", ""))).start()
