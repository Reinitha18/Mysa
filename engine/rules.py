"""
Couche de règles : détections explicables, sans apprentissage, appliquées à chaque message.

Le modèle comportemental (engine/analyzer.py) repère ce qui s'écarte de l'habitude d'un flux ;
il ne sait pas ce qui est physiquement impossible ni ce qui, par nature, est un incident de
sécurité. Ces règles couvrent ce que la référence TON_IoT ne voit pas (décalage de niveau,
valeurs hors contrat) et les événements d'accès, qui n'ont pas de « rythme » à apprendre.

Chaque règle déclenchée enregistre une alerte kind="rule" (source = nom de la règle) ;
les alertes d'un même flux et d'une même règle sont regroupées en épisodes par le stockage.
"""

import logging
from datetime import timedelta

from engine.storage import _parse, insert_alert, recent_values

log = logging.getLogger("mysa.rules")

# Plages physiques des capteurs (DHT22 : -40..80 °C, 0..100 %)
PHYSICAL_RANGE = {"temperature": (-40.0, 80.0), "humidity": (0.0, 100.0)}
TEMP_HIGH_C = 45.0            # au-delà : risque d'incendie / surchauffe
TEMP_JUMP_C = 5.0             # variation max plausible...
TEMP_JUMP_WINDOW_S = 60       # ...sur cette durée
REFUSED_BURST = 3             # badges refusés...
REFUSED_WINDOW_S = 60         # ...sur cette durée -> tentatives répétées (le nœud bloque le lecteur à 5)


def _alert(device_id, sensor, ts, rule, message, severity):
    info = insert_alert(device_id=device_id, message=message, severity=severity, ts=ts, sensor=sensor,
                        source=f"règle : {rule}", kind="rule")
    (log.warning if info["new_episode"] else log.debug)(message)
    return {"rule": rule, "severity": severity, "message": message}


def evaluate(device_id: str, sensor: str, value: float, unit: str | None, ts: str,
             meta: dict | None = None) -> list[dict]:
    """Applique les règles au message reçu ; retourne les alertes levées."""
    meta = meta or {}
    out = []
    where = f"{device_id}/{sensor}"

    # Contrat des capteurs binaires : une valeur autre que 0/1 est forgée (injection) ou un défaut.
    if unit == "bool" and value not in (0.0, 1.0):
        out.append(_alert(device_id, sensor, ts, "valeur hors contrat",
                          f"{where} : valeur {value:g} impossible pour un capteur binaire "
                          "(message forgé ou nœud défaillant)", "high"))
        return out

    if sensor in PHYSICAL_RANGE:
        lo, hi = PHYSICAL_RANGE[sensor]
        if not lo <= value <= hi:
            out.append(_alert(device_id, sensor, ts, "valeur hors contrat",
                              f"{where} : {value:g} {unit or ''} hors de la plage physique du capteur "
                              f"[{lo:g} ; {hi:g}] (message forgé ou capteur défaillant)", "high"))
            return out

    if sensor == "temperature":
        if value >= TEMP_HIGH_C:
            out.append(_alert(device_id, sensor, ts, "surchauffe",
                              f"Température très élevée sur {device_id} : {value:.1f} °C "
                              "(risque d'incendie ou de surchauffe)", "high"))
        since = (_parse(ts) - timedelta(seconds=TEMP_JUMP_WINDOW_S)).isoformat()
        previous = [r["value"] for r in recent_values(device_id, sensor, since)[:-1]]
        if previous and max(abs(value - p) for p in previous) > TEMP_JUMP_C:
            ref = max(previous, key=lambda p: abs(value - p))
            out.append(_alert(device_id, sensor, ts, "variation brutale",
                              f"Température de {device_id} passée de {ref:.1f} à {value:.1f} °C en moins "
                              f"de {TEMP_JUMP_WINDOW_S} s (source de chaleur, capteur manipulé ou message forgé)",
                              "medium"))

    elif sensor == "rfid" and value == 0.0:
        # Un badge refusé isolé (erreur de badge, visiteur) n'est pas une alerte : il est consigné
        # dans le journal des accès avec sa photo (engine.ingest). Seule la répétition alerte.
        since = (_parse(ts) - timedelta(seconds=REFUSED_WINDOW_S)).isoformat()
        refused = sum(1 for r in recent_values(device_id, sensor, since) if r["value"] == 0.0)
        if refused >= REFUSED_BURST:
            out.append(_alert(device_id, sensor, ts, "accès refusés répétés",
                              f"{refused} badges refusés en moins de {REFUSED_WINDOW_S} s sur {device_id} "
                              "(tentatives répétées : erreur de badge ou essai de force brute)", "medium"))

    elif sensor == "rfid_lockout" and value > 0:
        # value = durée du blocage en secondes (1 avec un firmware antérieur qui publiait un booléen)
        duration = f" pendant {value:g} s" if value > 1 else ""
        out.append(_alert(device_id, sensor, ts, "lecteur bloqué",
                          f"Lecteur de badges de {device_id} bloqué{duration} après plusieurs refus "
                          "(force brute probable)", "high"))

    elif sensor == "alarm" and value == 1.0:
        cause = meta.get("cause") or "cause non précisée"
        out.append(_alert(device_id, sensor, ts, "alarme",
                          f"Alarme déclenchée sur {device_id} : {cause}", "high"))

    elif sensor == "dht_error" and value == 1.0:
        out.append(_alert(device_id, sensor, ts, "capteur en défaut",
                          f"Lecture du DHT22 impossible sur {device_id} (câblage ou capteur arraché)", "medium"))

    elif sensor == "motion" and value == 1.0 and meta.get("armed"):
        out.append(_alert(device_id, sensor, ts, "mouvement filmé",
                          f"Mouvement détecté par la caméra {device_id} alors que l'alarme est armée", "high"))

    return out
