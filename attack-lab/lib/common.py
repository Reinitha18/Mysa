"""
Outils communs aux scénarios d'intrusion Mysa (TI-01 à TI-05), exécutés depuis la VM Kali.

⚠️ Usage strictement limité au prototype Mysa, sur un réseau de laboratoire isolé (GNS3), dans le
cadre du mémoire. Ne jamais lancer contre un système dont on n'est pas propriétaire.

Configuration par variables d'environnement (voir attack-lab/lab.env.example) :
  TARGET_HOST   IP du hub (défaut 192.168.30.20)
  MQTT_PORT     port du broker (défaut 8883)
  CA_CERT       chemin du certificat de la CA Mysa (pour établir le TLS ; le reste — auth, ACL —
                est la vraie barrière). Vide = TLS sans vérification de la chaîne.
  API_BASE      base de l'API pour MESURER la détection côté défenseur (défaut https://<host>:8000)
  DASHBOARD_EMAIL      adresse e-mail d'un compte du dashboard (vide : ancien mot de passe unique du hub)
  DASHBOARD_PASSWORD   mot de passe de ce compte (ou MYSA_DASHBOARD_PASSWORD du hub), si l'API est protégée :
                lecture de la détection et envoi du résultat de la campagne au journal de validation.
  STOLEN_USER / STOLEN_PASSWORD   identifiants d'un nœud supposé compromis (défaut esp32-sec-01),
                pour les scénarios qui exigent un accès authentifié (injection, saturation).

Chaque scénario expose run(cfg) -> dict : {ti, nom, execute, bloque, note, evidence}.
« bloqué » = l'attaque n'a pas pu s'exécuter (TLS/auth/ACL l'ont empêchée).
La DÉTECTION (alerte Mysa + délai) est mesurée séparément par run_report.py via l'API.
"""

import http.cookiejar
import json
import os
import ssl
import time
import urllib.request

import paho.mqtt.client as mqtt


def load_cfg() -> dict:
    host = os.getenv("TARGET_HOST", "192.168.30.20")
    return {
        "host": host,
        "mqtt_port": int(os.getenv("MQTT_PORT", "8883")),
        "ca_cert": os.getenv("CA_CERT") or None,
        "api_base": os.getenv("API_BASE", f"https://{host}:8000"),
        "dashboard_email": os.getenv("DASHBOARD_EMAIL") or None,
        "dashboard_password": os.getenv("DASHBOARD_PASSWORD") or None,
        "stolen_user": os.getenv("STOLEN_USER", "esp32-sec-01"),
        "stolen_password": os.getenv("STOLEN_PASSWORD", "change-me"),
    }


def mqtt_client(client_id: str, cfg: dict, user=None, password=None, use_tls=True) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    if user is not None:
        c.username_pw_set(user, password)
    if use_tls:
        c.tls_set(ca_certs=cfg["ca_cert"], cert_reqs=ssl.CERT_REQUIRED if cfg["ca_cert"] else ssl.CERT_NONE)
        if not cfg["ca_cert"]:
            c.tls_insecure_set(True)
    return c


def _rc_int(rc) -> int:
    """Code de retour MQTT en entier (paho v2 renvoie un ReasonCode, pas un int)."""
    v = getattr(rc, "value", rc)
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def try_connect(cfg: dict, user=None, password=None, use_tls=True, timeout=5.0) -> tuple[bool, str]:
    """Tente une connexion au broker. Retourne (connecté ?, détail). Ne lève pas.
    Boucle réseau BORNÉE (pas de loop_start, qui réessaierait indéfiniment sur un échec)."""
    state = {"rc": None}
    c = mqtt_client("ti-probe", cfg, user, password, use_tls)
    c.on_connect = lambda cl, u, f, rc, props=None: state.__setitem__("rc", _rc_int(rc))
    try:
        c.connect(cfg["host"], cfg["mqtt_port"], keepalive=10)
    except Exception as err:
        return False, f"connexion impossible : {err}"
    t0 = time.time()
    try:
        while state["rc"] is None and time.time() - t0 < timeout:
            c.loop(timeout=0.2)
    except Exception as err:
        detail = f"erreur réseau : {err}"
    else:
        detail = None
    try:
        c.disconnect()
    except Exception:
        pass
    if detail:
        return False, detail
    if state["rc"] is None:
        return False, "pas de réponse (TLS refusé ou port filtré)"
    return state["rc"] == 0, f"code de retour MQTT {state['rc']}"


def publish(cfg: dict, user, password, topic, payload, use_tls=True, timeout=5.0) -> tuple[bool, str]:
    """Publie un message (QoS 1) et attend le PUBACK. Retourne (confirmé ?, détail).
    Une publication refusée par l'ACL n'est jamais acquittée : elle revient « non confirmée »,
    ce qui distingue un envoi bloqué par l'ACL d'un envoi accepté."""
    ok, detail = try_connect(cfg, user, password, use_tls, timeout)
    if not ok:
        return False, f"connexion refusée ({detail})"
    c = mqtt_client("ti-pub", cfg, user, password, use_tls)
    try:
        c.connect(cfg["host"], cfg["mqtt_port"], keepalive=10)
        info = c.publish(topic, payload if isinstance(payload, str) else json.dumps(payload), qos=1)
        t0 = time.time()
        while not info.is_published() and time.time() - t0 < timeout:
            c.loop(timeout=0.2)
        confirmed = info.is_published()
        c.disconnect()
        return confirmed, "publié (acquitté)" if confirmed else "non acquitté (ACL ?)"
    except Exception as err:
        return False, f"échec de publication : {err}"


_opener = None


def _api_opener(cfg: dict):
    """Client HTTP de l'API du hub : TLS non vérifié (auto-signé) et cookie de session. Si le dashboard est
    protégé par mot de passe, la connexion se fait une seule fois, au premier appel."""
    global _opener
    if _opener is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                              urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        if cfg.get("dashboard_password"):
            api_post(cfg, "/api/auth/login", {"email": cfg.get("dashboard_email"), "password": cfg["dashboard_password"]},
                     _opener=_opener)
    return _opener


def api_get(cfg: dict, path: str, timeout=5.0):
    """Lecture de l'API du hub (mesure de la détection côté défenseur)."""
    with _api_opener(cfg).open(cfg["api_base"].rstrip("/") + path, timeout=timeout) as r:
        return json.loads(r.read())


def api_post(cfg: dict, path: str, body: dict, timeout=10.0, _opener=None):
    """Envoi JSON à l'API du hub (journal de validation, connexion)."""
    req = urllib.request.Request(cfg["api_base"].rstrip("/") + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with (_opener or _api_opener(cfg)).open(req, timeout=timeout) as r:
        return json.loads(r.read())
