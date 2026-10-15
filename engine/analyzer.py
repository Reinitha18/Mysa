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
REF_MAX_FLAG_RATE des REF_CHECK_WINDOWS premières fenêtres, elle est jugée
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
from engine.storage import insert_alert

log = logging.getLogger("mysa.analyzer")

STRIDE = 5          # un échantillon d'apprentissage tous les STRIDE messages
N_LOCAL_MIN = model.MIN_TRAIN_SAMPLES
N_LOCAL_MAX = 200
REFIT_EVERY = 20
REF_CHECK_WINDOWS = 10
REF_MAX_FLAG_RATE = 0.5

_state: dict[str, dict] = {}


def _get_state(key: str, sensor: str) -> dict:
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
        }
        log.info("Flux %s : catégorie=%s, référence=%s", key, category,
                 "oui" if _state[key]["ref"] else "non")
    return _state[key]


def evaluate(device_id: str, sensor: str):
    key = f"{device_id}__{sensor}".replace("/", "_")
    current = feat.extract_features(device_id, sensor)
    if not current:
        return  # fenêtre pas encore pleine pour ce flux

    st = _get_state(key, sensor)
    st["seen"] += 1

    result, source = None, None
    if model.has_baseline(key):
        result, source = model.score(key, current), "modèle local"
    elif st["ref"]:
        result = reference.score_reference(st["ref"], current)
        source = f"référence « {st['category']} »"

    anomalous = bool(result and result["is_anomaly"])

    if source and source.startswith("référence"):
        st["ref_eval"] += 1
        st["ref_flag"] += int(anomalous)
        if (st["ref_eval"] == REF_CHECK_WINDOWS
                and st["ref_flag"] / st["ref_eval"] > REF_MAX_FLAG_RATE):
            st["ref"] = None
            notice = (f"Référence « {st['category']} » inadaptée à {device_id}/{sensor} : "
                      "apprentissage depuis zéro")
            insert_alert(device_id=device_id, message=notice, severity="low")
            log.warning(notice)
    if anomalous:
        message = (f"Comportement inhabituel détecté sur {device_id}/{sensor} "
                   f"({source}, score {result['score']:.3f})")
        insert_alert(device_id=device_id, message=message, severity="high")
        log.warning(message)
        return  # fenêtre anormale : exclue de l'apprentissage

    if st["seen"] % STRIDE:
        return
    st["history"].append(current)
    st["since_fit"] += 1
    n = len(st["history"])

    if not model.has_baseline(key):
        log.info("Baseline %s : %d/%d échantillons", key, n, N_LOCAL_MIN)
        if n >= N_LOCAL_MIN and model.train_baseline(key, list(st["history"])):
            st["since_fit"] = 0
            log.info("Modèle local entraîné pour %s — il remplace la référence", key)
    elif st["since_fit"] >= REFIT_EVERY:
        model.train_baseline(key, list(st["history"]))
        st["since_fit"] = 0
        log.info("Modèle local de %s ré-entraîné sur %d échantillons", key, n)
