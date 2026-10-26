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

Protection contre l'empoisonnement de la baseline : une fenêtre jugée anormale
(par la référence ou par le modèle local) n'est JAMAIS ajoutée à
l'historique d'apprentissage.

Limite assumée : l'historique d'apprentissage est en mémoire (perdu au
redémarrage tant que le premier modèle local n'est pas entraîné).
"""

import logging
from collections import deque

from engine import features as feat
from engine import model, reference
from engine.categories import categorize
from datetime import datetime, timezone

from engine.storage import insert_alert, upsert_stream

log = logging.getLogger("mysa.analyzer")

STRIDE = 5          # un échantillon d'apprentissage tous les STRIDE messages
N_LOCAL_MIN = model.MIN_TRAIN_SAMPLES  # 40 échantillons, soit 215 messages au minimum
N_LOCAL_MAX = 200
REFIT_EVERY = 20
REF_CHECK_WINDOWS = 10
REF_MAX_FLAG_RATE = 0.5
REF_ROLLING_WINDOWS = 100  # contrôle durable : la référence peut se dégrader après un bon début

_state: dict[str, dict] = {}
_published: dict[str, tuple] = {}


def _get_state(key: str, sensor: str, unit: str | None = None) -> dict:
    if key not in _state:
        category = categorize(sensor)
        _state[key] = {
            "category": category,
            "ref": reference.load_reference(category),
            "history": deque(maxlen=N_LOCAL_MAX),
            "seen": 0,
            "since_fit": 0,
            "ref_eval": 0,
            "ref_flag": 0,
            "ref_rejected": False,
            "ref_recent": deque(maxlen=REF_ROLLING_WINDOWS),
            "binary": unit == "bool",
        }
        log.info("Flux %s : catégorie=%s, référence=%s", key, category,
                 "oui" if _state[key]["ref"] else "non")
    return _state[key]


def _key(device_id: str, sensor: str) -> str:
    return f"{device_id}__{sensor}".replace("/", "_")


def _evaluate(device_id: str, sensor: str, ts: str, unit: str | None = None):
    key = _key(device_id, sensor)
    current = feat.extract_features(device_id, sensor)
    if not current:
        return  # fenêtre pas encore pleine pour ce flux

    st = _get_state(key, sensor, unit)
    st["seen"] += 1

    result, source = None, None
    if model.has_baseline(key):
        result = model.score(key, current)
        source = "modèle local"
    elif st["ref"]:
        result = reference.score_reference(st["ref"], current)
        source = f"référence « {st['category']} »"

    anomalous = bool(result and result["is_anomaly"])

    if source and source.startswith("référence"):
        st["ref_eval"] += 1
        st["ref_flag"] += int(anomalous)
        st["ref_recent"].append(int(anomalous))
        quick = (st["ref_eval"] == REF_CHECK_WINDOWS
                 and st["ref_flag"] / st["ref_eval"] > REF_MAX_FLAG_RATE)
        sustained = (len(st["ref_recent"]) == REF_ROLLING_WINDOWS
                     and sum(st["ref_recent"]) / REF_ROLLING_WINDOWS > REF_MAX_FLAG_RATE)
        if quick or sustained:
            st["ref"] = None
            st["ref_rejected"] = True
            notice = (f"Référence « {st['category']} » inadaptée à {device_id}/{sensor} : "
                      "apprentissage depuis zéro")
            insert_alert(device_id=device_id, message=notice, severity="low", ts=ts, sensor=sensor,
                         source="garde de compatibilité", kind="notice")
            log.warning(notice)

    if anomalous:
        detail = f", {result['reason']}" if result.get("reason") else ""
        message = (f"Comportement inhabituel détecté sur {device_id}/{sensor} "
                   f"({source}{detail}, score {result['score']:.3f})")
        label = f"{source} ({result['reason']})" if result.get("reason") else source
        info = insert_alert(device_id=device_id, message=message, severity="high", ts=ts, sensor=sensor,
                            source=label, score=result["score"], kind="anomaly")
        # Une seule ligne de journal par épisode : les alertes suivantes de la grappe sont consignées en base.
        (log.warning if info["new_episode"] else log.debug)(message)
        return  # fenêtre anormale : exclue de l'apprentissage

    if st["seen"] % STRIDE:
        return
    st["history"].append(current)
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


def evaluate(device_id: str, sensor: str, ts: str | None = None, unit: str | None = None):
    """Évalue le flux (device_id, sensor) après réception d'un message.
    `ts` : horodatage du message (sert à regrouper les alertes en épisodes)."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    _evaluate(device_id, sensor, ts, unit)
    _publish_state(device_id, sensor)
