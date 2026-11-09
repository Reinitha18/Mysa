# Lab d'attaque Mysa

Scénarios d'intrusion automatisés, exécutés depuis la **VM Kali** (VLAN 40 dans GNS3), pour éprouver
les défenses du prototype Mysa et produire le tableau de résultats « avant / après » du chapitre 9
du mémoire. Chaque scénario est relié à un risque évalué au chapitre 4 (R-01 à R-05).

> ⚠️ **Cadre autorisé uniquement.** Ces outils ne doivent viser que le prototype Mysa, dont tu es
> propriétaire, sur un réseau de laboratoire **isolé** (GNS3). Ne jamais les utiliser contre un
> système tiers.

Plateforme volontairement **séparée** du dashboard Mysa (aucun code partagé) : l'attaquant ne
dispose que de ce qu'un adversaire réel aurait (accès réseau, éventuellement un identifiant de nœud
volé). L'API du hub n'est lue que par `run_report.py`, en position de **défenseur**, pour mesurer la
détection.

## Scénarios

| TI | Risque | Attaque | Défense attendue de Mysa |
|----|--------|---------|--------------------------|
| **TI-01** | R-01 | Écoute du trafic MQTT (anonyme, en clair) | TLS + authentification obligatoires → **bloqué** |
| **TI-02** | R-02 | Force brute des identifiants du broker | Mots de passe forts → **bloqué** |
| **TI-03** | R-03 | Usurpation d'un nœud, injection de télémétrie et de commandes | ACL du broker (usurpation/commande **bloquées**) + règle « valeur hors contrat » (**détection**) |
| **TI-04** | R-04 | Saturation (inondation de messages) | Détecteur de rythme du moteur (**détection** une fois le modèle appris) |
| **TI-05** | R-05 | Attaque du canal caméra (injection, écoute) | **Segmentation réseau** (pare-feu GNS3 : seuls les objets joignent le hub) |

## Installation (VM Kali)

```bash
bash attack-lab/install.sh
```
Installe `nmap`, `mosquitto-clients`, `hydra`, et les modules Python `paho-mqtt` /
`websocket-client`. Copie ensuite `broker/certs/ca.crt` du hub vers la VM et renseigne
`attack-lab/lab.env` (voir `lab.env.example`).

## Lancer

```bash
set -a; source attack-lab/lab.env; set +a                     # charge la configuration
python3 attack-lab/run_report.py --out attack-lab/report.md   # tout + rapport avant/après + journal du dashboard
python3 attack-lab/scenarios/ti03_usurpation.py               # un scénario isolé
```

La campagne est aussi **journalisée dans le dashboard** (page « Validation » : résultat de chaque TI, délai de
détection, alertes levées par Mysa pendant l'attaque) ; `--no-push` désactive cet envoi. Si le dashboard est
protégé par mot de passe, renseigner `DASHBOARD_EMAIL` et `DASHBOARD_PASSWORD` dans `lab.env` (un compte du dashboard ; sans e-mail, l'ancien mot de passe unique).

Le rapport `report.md` indique, pour chaque TI : résultat **avant** (système non durci, analyse du
chapitre 4) et **après** (mesuré : bloqué / détecté avec délai / exécuté non détecté).

## Fichiers

```
install.sh              installation des outils sur Kali
lab.env.example         configuration (cible, CA, identifiants volés…)
lib/common.py           connexion broker/API, publication, mesure
scenarios/ti01..ti05    les cinq scénarios d'intrusion
run_report.py           exécute tout et génère report.md (avant/après)
```

Voir `docs/kali.md` pour l'import de la VM Kali et son rattachement au réseau GNS3.
