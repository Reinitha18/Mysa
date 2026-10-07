"""
Orchestration de la détection comportementale : pour chaque nouveau message
reçu par le moteur d'ingestion, on calcule les caractéristiques de l'appareil
concerné puis, selon qu'une baseline existe déjà ou non pour lui :
  - si la baseline n'existe pas encore -> on accumule l'échantillon, et on
    déclenche l'apprentissage une fois qu'on en a assez (BASELINE_SIZE) ;
  - si la baseline existe -> on évalue l'échantillon courant et on déclenche
    une alerte en cas d'écart significatif.

Simplification assumée pour ce stade du prototype : l'historique de
caractéristiques utilisé pour l'apprentissage est conservé en mémoire
(_feature_history), donc perdu si le moteur redémarre avant que la baseline
soit construite. C'est une limite déjà identifiée au chapitre 5.6 du
mémoire ; un historique persistant (fichier ou table dédiée) pourra la lever
si le projet est étendu au-delà du prototype.
"""

import logging

from engine import features as feat
from engine import model
from engine.storage import insert_alert

log = logging.getLogger("mysa.analyzer")

BASELINE_SIZE = 20

_feature_history: dict[str, list[dict]] = {}


def evaluate(device_id: str):
    current = feat.extract_features(device_id)
    if not current:
        return  # pas encore assez de télémétrie pour cet appareil

    if model.has_baseline(device_id):
        result = model.score(device_id, current)
        if result and result["is_anomaly"]:
            message = f"Comportement inhabituel détecté sur {device_id} (score {result['score']:.3f})"
            insert_alert(device_id=device_id, message=message, severity="high")
            log.warning(message)
        return

    history = _feature_history.setdefault(device_id, [])
    history.append(current)
    log.info("Baseline %s : %d/%d échantillons", device_id, len(history), BASELINE_SIZE)

    if len(history) >= BASELINE_SIZE:
        trained = model.train_baseline(device_id, history)
        if trained:
            log.info("Baseline entraînée pour %s — détection active désormais", device_id)
            _feature_history[device_id] = []
