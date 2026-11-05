> Exemple généré lors d'une validation locale (cible localhost, hub Docker). Sur le lab GNS3, la cible est le hub en 192.168.30.20.

# Lab d'attaque Mysa — rapport avant / après

_Généré le 2026-10-29 03:41 UTC — cible localhost._

« Avant » : résultat attendu sur le système non durci (analyse des vulnérabilités, chapitre 4). 
« Après » : résultat **mesuré** sur Mysa (bloqué par TLS/auth/ACL/pare-feu, ou détecté par le moteur).

| TI | Attaque | Avant (sans Mysa) | Après (Mysa) | Observations |
|----|---------|-------------------|--------------|--------------|
| TI-01 | Écoute du trafic MQTT | Réussie : trafic en clair, lecture possible (V-01) ; connexion anonyme (V-02). | 🛡️ Bloqué | connexion anonyme (TLS) : refusée (code de retour MQTT 135) ; connexion en clair : refusée (pas de réponse (TLS refusé ou port filtré)) |
| TI-02 | Force brute des identifiants | Réussie : identifiants par défaut / faibles (V-02). | 🛡️ Bloqué | 12 mots de passe essayés contre « mysa-engine » : aucun accepté (mot de passe résistant) |
| TI-03 | Usurpation / injection | Réussie : ni ACL ni validation — usurpation, commandes et télémétrie forgées acceptées. | 🔎 Détecté (~0 s) | usurpation esp32-cmf-01 : acquittée (doit être jetée par l'ACL) ; injection de commande cmd/lock : acquittée (doit être jetée par l'ACL) ; télémétrie forgée pir=999 : acquittée (détectée par la règle de contrat) \| ACL : usurpation de esp32-cmf-01 BLOQUÉE (aucune télémétrie reçue) |
| TI-04 | Saturation | Non détectée : aucune surveillance du rythme des messages. | ⚠️ Exécuté, non détecté | 300 messages envoyés en rafale (~295 msg/s) sur home/esp32-sec-01/pir |
| TI-05 | Attaque de la caméra | Réussie : flux caméra accessible, pas de cloisonnement. | ⚠️ Exécuté, non détecté | canal caméra ATTEINT (port 8000 accessible) ; faux mouvement injecté : True ; flux reçu (vie privée) : True. Protection = segmentation réseau (pare-feu GNS3). |

## Lecture
- **Bloqué** : l'attaque n'a pas pu s'exécuter (chiffrement, authentification, ACL du broker ou segmentation réseau l'en ont empêchée).
- **Détecté** : l'attaque s'est exécutée mais le moteur a levé une alerte (délai = temps jusqu'à la première alerte).
- **Exécuté, non détecté** : à analyser — p. ex. la saturation (TI-04) n'est détectée qu'une fois le modèle du flux appris (voir scripts/replay_eval.py, sc02), et le canal caméra (TI-05) est protégé par la segmentation réseau plutôt que par une détection applicative.
