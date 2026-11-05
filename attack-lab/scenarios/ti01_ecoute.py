"""TI-01 — Écoute du trafic MQTT (eavesdropping).

Risque visé : R-01 (confidentialité) / vulnérabilités V-01 (absence de chiffrement) et V-02
(connexion anonyme). L'attaquant tente de lire la télémétrie :
  a) en se connectant SANS identifiants (connexion anonyme) et en s'abonnant à home/# ;
  b) en se connectant en CLAIR (sans TLS) sur le port du broker.

Attendu sur Mysa durci : les deux échouent (auth obligatoire, TLS obligatoire) -> bloqué.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from common import load_cfg, try_connect  # noqa: E402


def run(cfg: dict) -> dict:
    anon_ok, anon_detail = try_connect(cfg, user=None, password=None, use_tls=True)
    clear_ok, clear_detail = try_connect(cfg, user=None, password=None, use_tls=False)
    blocked = not anon_ok and not clear_ok
    note = (f"connexion anonyme (TLS) : {'ACCEPTÉE' if anon_ok else 'refusée'} ({anon_detail}) ; "
            f"connexion en clair : {'ACCEPTÉE' if clear_ok else 'refusée'} ({clear_detail})")
    return {"ti": "TI-01", "nom": "Écoute du trafic MQTT", "execute": True, "bloque": blocked,
            "note": note, "evidence": None}


if __name__ == "__main__":
    print(run(load_cfg()))
