"""
Orchestration de la détection comportementale, par flux capteur
(clé = "<device_id>__<sensor>"), en trois régimes :

  1. AMORÇAGE : pas encore de modèle local. Si une catégorie est reconnue pour
     le capteur (engine/categories.py) et qu'un modèle de référence existe
     (engine/reference.py), c'est lui qui détecte dès la première fenêtre
     complète. Sinon, aucune détection (comportement de la version initiale).
  2. BASCULE : dès que N_LOCAL_MIN échantillons locaux jugés normaux sont
     accumulés, un modèle local est entraîné et remplace la référence.
  3. AFFINAGE : tous les REFIT_EVERY nouveaux échantillons normaux, le modèle
     local est ré-entraîné sur les N_LOCAL_MAX derniers (fenêtre glissante).

Garde de compatibilité : si la référence classe en anomalie plus de
REF_MAX_FLAG_RATE des REF_CHECK_WINDOWS premières fenêtres, OU des REF_ROLLING_WINDOWS
dernières fenêtres (contrôle durable), elle est jugée
inadaptée à ce flux (décalage entre le dataset public et l'appareil réel,
ou attaque dès le démarrage — indiscernables sans étiquette). Elle est alors
abandonnée, un avis est enregistré, et le flux apprend depuis zéro.

Rôle de la référence : FILTRE de la baseline, pas détecteur (REF_ALERTS = False par défaut).
Pendant l'amorçage, une fenêtre que la référence juge anormale n'entre pas dans l'historique
d'apprentissage, mais ne lève pas d'alerte. Mesures qui motivent ce choix :
  - hors ligne (mémoire, tableau 32), le taux de détection des références TON_IoT est
    inférieur ou voisin de leur taux de fausses alertes ;
  - sur les appareils virtuels (scripts/replay_eval.py, 5 graines), les références sont
    rejetées sur les quatre flux catégorisés à chaque run normal, et leurs alertes formaient
    l'essentiel des fausses alertes restantes (40 épisodes sur 20 runs, 12 sans elles,
    détection inchangée).
Une référence rejetée donne un seul avis (gravité « medium ») qui énonce les deux explications
possibles. MYSA_REFERENCE_ALERTS=1 rétablit les alertes de la référence (essais de
l'hypothèse H1), après une période probatoire de REF_CHECK_WINDOWS fenêtres sans alerte.

Confirmation des indices faibles : un signalement de la forêt ou de la référence (score
à peine sous le seuil) ne devient une alerte que si au moins CONFIRM_K des CONFIRM_M
dernières fenêtres du flux sont suspectes. Les indices forts du modèle local (enveloppe
de valeurs, rythme, tendance, bascules) déclenchent l'alerte immédiatement. Gravité : « high »
pour un indice fort, « medium » pour un indice faible confirmé.

Protection contre l'empoisonnement de la baseline : une fenêtre jugée anormale
(par la référence ou par le modèle local, confirmée ou non) n'est JAMAIS ajoutée à
l'historique d'apprentissage.

L'historique d'apprentissage est sauvegardé à chaque ajout (<clé>.history.joblib, à côté
des modèles locaux) : un redémarrage du moteur pendant l'apprentissage ne le perd plus.
"""

import logging
import os
from collections import deque
from datetime import datetime, timezone

import joblib

from engine import features as feat
from engine import model, reference
from engine.categories import categorize
from engine.storage import insert_alert, upsert_stream

log = logging.getLogger("mysa.analyzer")

STRIDE = 5          # un échantillon d'apprentissage tous les STRIDE messages
N_LOCAL_MIN = model.MIN_TRAIN_SAMPLES  # 40 échantillons, soit 215 messages au minimum
N_LOCAL_MAX = 200
REFIT_EVERY = 20
REF_CHECK_WINDOWS = 10
REF_MAX_FLAG_RATE = 0.5
REF_ROLLING_WINDOWS = 100  # contrôle durable : la référence peut se dégrader après un bon début
REF_ALERTS = os.getenv("MYSA_REFERENCE_ALERTS") == "1"  # la référence lève-t-elle des alertes ?
REF_PROBATION = True       # si oui, pas pendant ses REF_CHECK_WINDOWS premières fenêtres
CONFIRM_K = 2       # indices faibles : au moins CONFIRM_K fenêtres suspectes...
CONFIRM_M = 3       # ... parmi les CONFIRM_M dernières

REASON_TEXT = {
    "enveloppe": "valeurs hors de la plage habituelle",
    "rythme": "rythme de publication inhabituel",
    "tendance": "dérive progressive des valeurs",
    "bascules": "changements d'état incessants",
    "forêt": "combinaison inhabituelle de caractéristiques",
}

_state: dict[str, dict] = {}
_published: dict[str, tuple] = {}


# Après la reconnexion d'un nœud (Last Will), ses fenêtres contiennent forcément le trou de la
# coupure : le détecteur de rythme le signalerait sur chaque flux alors que la coupure est déjà
# signalée par la présence. Pendant RECONNECT_GRACE_S, une alerte de rythme n'est pas levée
# (la fenêtre reste exclue de l'apprentissage).
RECONNECT_GRACE_S = 120
_reconnected: dict[str, datetime] = {}


def note_reconnect(device_id: str, ts: str):
    _reconnected[device_id] = datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _in_grace(device_id: str, ts: str) -> bool:
    since = _reconnected.get(device_id)
    return since is not None and 0 <= (datetime.fromisoformat(ts.replace("Z", "+00:00")) - since).total_seconds() < RECONNECT_GRACE_S


def reset():
    """Oublie l'état en mémoire (tests, rejeu hors ligne)."""
    _state.clear()
    _published.clear()
    _reconnected.clear()


def _history_path(key: str) -> str:
    return os.path.join(model.MODELS_DIR, f"{key}.history.joblib")


def _load_history(key: str) -> deque:
    path = _history_path(key)
    items = []
    if os.path.exists(path):
        try:
            items = joblib.load(path)
        except Exception:  # fichier abîmé : on repart de zéro plutôt que d'arrêter le moteur
            log.warning("Historique d'apprentissage illisible pour %s : ignoré", key)
    return deque(items, maxlen=N_LOCAL_MAX)


def _save_history(key: str, history: deque):
    tmp = _history_path(key) + ".tmp"
    joblib.dump(list(history), tmp)
    os.replace(tmp, _history_path(key))


def _get_state(key: str, sensor: str, unit: str | None = None) -> dict:
    if key not in _state:
        category = categorize(sensor)
        history = _load_history(key)
        _state[key] = {
            "category": category,
            "ref": reference.load_reference(category),
            "history": history,
            "seen": 0,
            "since_fit": 0,
            "ref_eval": 0,
            "ref_flag": 0,
            "ref_rejected": False,
            "ref_recent": deque(maxlen=REF_ROLLING_WINDOWS),
            "recent": deque(maxlen=CONFIRM_M),
            "binary": unit == "bool",
        }
        log.info("Flux %s : catégorie=%s, référence=%s, historique repris=%d", key, category,
                 "oui" if _state[key]["ref"] else "non", len(history))
    return _state[key]


def _key(device_id: str, sensor: str) -> str:
    return f"{device_id}__{sensor}".replace("/", "_")


def _evaluate(device_id: str, sensor: str, ts: str, unit: str | None = None) -> dict | None:
    key = _key(device_id, sensor)
    current = feat.extract_features(device_id, sensor)
    if not current:
        return None  # fenêtre pas encore pleine pour ce flux

    st = _get_state(key, sensor, unit)
    st["seen"] += 1

    result, source = None, None
    if model.has_baseline(key):
        result = model.score(key, current)
        source = "modèle local"
    elif st["ref"]:
        result = reference.score_reference(st["ref"], current)
        source = f"référence « {st['category']} »"

    suspect = bool(result and result["is_anomaly"])
    st["recent"].append(suspect)

    if source and source.startswith("référence"):
        st["ref_eval"] += 1
        st["ref_flag"] += int(suspect)
        st["ref_recent"].append(int(suspect))
        quick = (st["ref_eval"] == REF_CHECK_WINDOWS
                 and st["ref_flag"] / st["ref_eval"] > REF_MAX_FLAG_RATE)
        sustained = (len(st["ref_recent"]) == REF_ROLLING_WINDOWS
                     and sum(st["ref_recent"]) / REF_ROLLING_WINDOWS > REF_MAX_FLAG_RATE)
        if quick or sustained:
            st["ref"] = None
            st["ref_rejected"] = True
            rate = (st["ref_flag"] / st["ref_eval"]) if quick else sum(st["ref_recent"]) / REF_ROLLING_WINDOWS
            notice = (f"Référence « {st['category']} » abandonnée pour {device_id}/{sensor} : "
                      f"{rate:.0%} des fenêtres s'en écartent. Soit l'appareil diffère du jeu de données "
                      "public, soit il se comporte anormalement depuis son installation — à vérifier. "
                      "Apprentissage depuis zéro.")
            insert_alert(device_id=device_id, message=notice, severity="medium", ts=ts, sensor=sensor,
                         source="garde de compatibilité", kind="notice")
            log.warning(notice)

    if suspect:
        strong = bool(result.get("strong"))
        confirmed = strong or sum(st["recent"]) >= CONFIRM_K
        if source.startswith("référence") and (
                not REF_ALERTS or st["ref"] is None or (REF_PROBATION and st["ref_eval"] <= REF_CHECK_WINDOWS)):
            confirmed = False  # référence : filtre de la baseline seulement (voir en tête de module)
        if result.get("reason") == "rythme" and _in_grace(device_id, ts):
            confirmed = False  # trou de la coupure, déjà signalé par la présence
        if confirmed:
            reason = result.get("reason")
            label = f"{source} ({reason})" if reason else source
            what = REASON_TEXT.get(reason, "comportement différent de la référence de sa catégorie")
            message = (f"Comportement inhabituel détecté sur {device_id}/{sensor} : {what} "
                       f"({label}, score {result['score']:.3f})")
            info = insert_alert(device_id=device_id, message=message, severity="high" if strong else "medium",
                                ts=ts, sensor=sensor, source=label, score=result["score"], kind="anomaly")
            # Une seule ligne de journal par épisode : les alertes suivantes de la grappe sont consignées en base.
            (log.warning if info["new_episode"] else log.debug)(message)
        return {"suspect": True, "alert": confirmed, "source": source, **result}  # exclue de l'apprentissage

    if st["seen"] % STRIDE == 0:
        _learn(key, st, current)
    return {"suspect": False, "alert": False, "source": source, **(result or {})}


def _learn(key: str, st: dict, current: dict):
    st["history"].append(current)
    _save_history(key, st["history"])
    st["since_fit"] += 1
    n = len(st["history"])

    if not model.has_baseline(key):
        log.info("Baseline %s : %d/%d échantillons", key, n, N_LOCAL_MIN)
        if n >= N_LOCAL_MIN and model.train_baseline(key, list(st["history"]), st["binary"]):
            st["since_fit"] = 0
            log.info("Modèle local entraîné pour %s — il remplace la référence", key)
    elif st["since_fit"] >= REFIT_EVERY:
        model.train_baseline(key, list(st["history"]), st["binary"])
        st["since_fit"] = 0
        log.info("Modèle local de %s ré-entraîné sur %d échantillons", key, n)


def _publish_state(device_id: str, sensor: str):
    """Écrit l'état du flux en base pour que l'API (autre processus) puisse l'afficher."""
    key = _key(device_id, sensor)
    st = _state.get(key)
    if st is None:  # fenêtre de 20 messages pas encore pleine
        category = categorize(sensor)
        has_ref = reference.load_reference(category) is not None
        snapshot = (category, "démarrage", "disponible" if has_ref else "aucune", 0)
        if _published.get(key) != snapshot:
            upsert_stream(device_id, sensor, category=category, regime="démarrage",
                          ref_status=snapshot[2], local_samples=0)
            _published[key] = snapshot
        return
    if model.has_baseline(key):
        regime = "local"
    elif st["ref"]:
        regime = "référence"
    else:
        regime = "apprentissage"
    ref_status = "rejetée" if st["ref_rejected"] else ("active" if st["ref"] else "aucune")
    snapshot = (st["category"], regime, ref_status, len(st["history"]))
    if _published.get(key) != snapshot:  # écriture seulement si l'état a changé
        upsert_stream(device_id, sensor, category=st["category"], regime=regime, ref_status=ref_status,
                      local_samples=len(st["history"]))
        _published[key] = snapshot


def evaluate(device_id: str, sensor: str, ts: str | None = None, unit: str | None = None) -> dict | None:
    """Évalue le flux (device_id, sensor) après réception d'un message.
    `ts` : horodatage du message (sert à regrouper les alertes en épisodes).
    Retourne le verdict de la fenêtre (None tant qu'elle n'est pas pleine)."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    verdict = _evaluate(device_id, sensor, ts, unit)
    _publish_state(device_id, sensor)
    return verdict
