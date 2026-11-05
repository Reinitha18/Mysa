"""TI-02 — Force brute des identifiants du broker.

Risque visé : R-02 (contrôle d'accès) / V-02 (identifiants faibles ou par défaut). L'attaquant
essaie une liste de mots de passe courants contre un compte connu (par défaut mysa-engine).

Attendu sur Mysa durci (mots de passe forts générés au déploiement) : aucun essai accepté -> bloqué.
Le scénario illustre pourquoi des mots de passe forts sont indispensables : si un mot de passe
faible figure dans la liste, il est trouvé immédiatement.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from common import load_cfg, try_connect  # noqa: E402

TARGET_USER = os.getenv("BRUTE_USER", "mysa-engine")
# Petite liste de mots de passe courants (extrait type rockyou). En production, utiliser une vraie
# liste ; ici, de quoi montrer la méthode sans dépendance externe.
WORDLIST = ["admin", "password", "123456", "mosquitto", "mqtt", "root", "iot", "mysa",
            "changeme", "default", "toor", "raspberry"]


def run(cfg: dict) -> dict:
    tried, found = 0, None
    for pw in WORDLIST:
        tried += 1
        ok, _ = try_connect(cfg, user=TARGET_USER, password=pw, use_tls=True, timeout=4.0)
        if ok:
            found = pw
            break
    blocked = found is None
    note = (f"{tried} mots de passe essayés contre « {TARGET_USER} » : "
            + (f"TROUVÉ « {found} » — mot de passe trop faible !" if found
               else "aucun accepté (mot de passe résistant)"))
    return {"ti": "TI-02", "nom": "Force brute des identifiants", "execute": True, "bloque": blocked,
            "note": note, "evidence": None}


if __name__ == "__main__":
    print(run(load_cfg()))
