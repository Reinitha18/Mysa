"""TI-03 — Usurpation d'un nœud, injection de télémétrie et de commandes.

Risque visé : R-03 (intégrité). On suppose un nœud COMPROMIS : l'attaquant détient les identifiants
de esp32-sec-01 (STOLEN_USER/STOLEN_PASSWORD). Trois tentatives :
  a) Usurpation d'un AUTRE nœud : publier sous home/esp32-cmf-01/... -> doit être bloqué par l'ACL.
  b) Injection d'une COMMANDE : publier home/esp32-cmf-01/cmd/lock -> doit être bloqué par l'ACL.
  c) Injection de TÉLÉMÉTRIE forgée sur son propre topic : home/esp32-sec-01/pir = 999 (valeur
     impossible pour un capteur binaire) -> l'ACL laisse passer, mais la règle « valeur hors contrat »
     de Mysa doit lever une alerte « high ».

Le blocage (a,b) et la détection (c) sont mesurés côté défenseur par run_report.py.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from common import load_cfg, publish  # noqa: E402


def run(cfg: dict) -> dict:
    u, p = cfg["stolen_user"], cfg["stolen_password"]
    since = datetime.now(timezone.utc).isoformat()

    spoof_ok, spoof_detail = publish(cfg, u, p, "home/esp32-cmf-01/pir",
                                     {"value": 1, "unit": "bool"})
    cmd_ok, cmd_detail = publish(cfg, u, p, "home/esp32-cmf-01/cmd/lock", "open")
    inject_ok, inject_detail = publish(cfg, u, p, "home/esp32-sec-01/pir",
                                       {"value": 999, "unit": "bool"})

    # Le broker ACQUITTE un QoS 1 même quand l'ACL jette ensuite le message : l'acquittement ne
    # prouve donc pas la livraison. La preuve du blocage se lit côté défenseur (run_report).
    note = (f"usurpation esp32-cmf-01 : {'acquittée' if spoof_ok else spoof_detail} (doit être jetée par l'ACL) ; "
            f"injection de commande cmd/lock : {'acquittée' if cmd_ok else cmd_detail} (doit être jetée par l'ACL) ; "
            f"télémétrie forgée pir=999 : {'acquittée' if inject_ok else inject_detail} (détectée par la règle de contrat)")
    return {"ti": "TI-03", "nom": "Usurpation / injection", "execute": True, "bloque": False,
            "note": note,
            # Détection attendue côté Mysa : la valeur hors contrat forgée.
            "evidence": {"since": since, "device_id": "esp32-sec-01", "sensor": "pir",
                         "attendu": "valeur hors contrat",
                         "acl": {"usurpation_cmf": "home/esp32-cmf-01/pir",
                                 "commande": "home/esp32-cmf-01/cmd/lock"}}}


if __name__ == "__main__":
    print(run(load_cfg()))
