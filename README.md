# Mysa

Architecture autonome de cybersécurité comportementale pour les écosystèmes de maisons intelligentes.

Projet de fin d'études — voir le mémoire pour le détail de l'analyse, de la conception et des choix techniques.

## Structure du dépôt

```
mysa/
  engine/       -> moteur de détection comportementale (règles, corrélation, modèle, notifications)
  api/          -> API FastAPI (données, commandes, pont caméra) qui sert aussi le dashboard
  broker/       -> configuration du broker MQTT (Mosquitto : TLS + ACL)
  firmware/     -> code embarqué des deux nœuds ESP32 (sec-01, cmf-01)
  dashboard/    -> interface web de supervision (React)
  camera/       -> page caméra du téléphone (HTML/JS)
  attack-lab/   -> scénarios d'intrusion TI-01..05 (VM Kali) + rapport avant/après
  deploy/       -> scripts de démarrage Windows (Docker)
  gns3/         -> réseau segmenté (routeur OpenWrt, VLAN, matrice de flux)
  docs/         -> guides (déploiement Windows, GNS3, HTTPS, notifications, démo, fiche produit…)
```

**Déploiement sous Windows** : double-clic sur `Demarrer Mysa.bat` (broker + moteur + API/dashboard/caméra
dans Docker), puis `Televerser sec01.bat` / `Televerser cmf01.bat` pour les nœuds et `Verifier Mysa.bat`.
Guide pas à pas : `docs/deploiement_windows.md` ; réseau segmenté : `docs/gns3.md`.

Tous les réglages sont dans `.env` (modèle : `.env.example`) : IP du hub, Wi-Fi des nœuds, mots de passe,
notifications. Le firmware les lit à la compilation avec la CA du hub (`firmware/scripts/gen_config.py`).

## Démarrage rapide (moteur + API)

1. Créer un environnement virtuel Python :
   ```
   python -m venv .venv
   ```
2. L'activer :
   - Windows : `.venv\Scripts\activate`
   - Mac/Linux : `source .venv/bin/activate`
3. Installer les dépendances :
   ```
   pip install -r requirements.txt
   ```
4. Copier `.env.example` vers `.env` et ajuster les valeurs (adresse du broker, identifiants).
5. Lancer l'API (elle initialise automatiquement la base de données locale) :
   ```
   uvicorn api.main:app --reload
   ```
6. Dans un second terminal, lancer le moteur d'ingestion (nécessite un broker MQTT accessible) :
   ```
   python -m engine.ingest
   ```

L'API est alors disponible sur http://127.0.0.1:8000 (documentation interactive sur /docs).
Une fois le dashboard compilé (`cd dashboard && npm install && npm run build`), il est servi sur
http://127.0.0.1:8000/dashboard/. Démonstration sans broker : `python scripts/demo_seed.py` (voir dashboard/README.md).

## Tester la boucle complète (baseline + détection)

Avec Mosquitto local (mosquitto -c mosquitto-local.conf -v) lancé et `python -m engine.ingest` dans un terminal,
lance dans un autre terminal :
```
python scripts/simulate_device.py
```
Ce script publie 150 messages "normaux" (de quoi construire une baseline locale),
puis un message franchement anormal. Le terminal de l'ingestion doit afficher
la progression de l'apprentissage, puis une alerte sur le dernier message.
Vérifiable aussi via http://127.0.0.1:8000/api/alerts.

## État d'avancement

- [x] Moteur d'ingestion MQTT -> base de données locale (topic contrôlé contre l'usurpation)
- [x] API de consultation (appareils, alertes, épisodes, flux, score de risque, WebSocket)
- [x] Extraction de caractéristiques comportementales (engine/features.py)
- [x] Modèle local à quatre détecteurs : forêt calibrée, enveloppes de valeurs et de rythme, tendance (engine/model.py)
- [x] Orchestration baseline -> détection -> confirmation -> alerte (engine/analyzer.py)
- [x] Catégories d'appareils et modèles de référence pour l'amorçage à froid (engine/categories.py, engine/reference.py, scripts/train_reference.py)
- [x] Chien de garde des appareils silencieux (engine/watchdog.py)
- [x] Score de risque par appareil (engine/risk.py)
- [x] Banc d'essai hors ligne et tests automatisés (scripts/replay_eval.py, tests/)
- [x] Dashboard React (dashboard/README.md) et commandes des actionneurs via l'API
- [x] Corrélation entre capteurs (engine/correlation.py) : mouvement+alarme, PIR+caméra, heure inhabituelle
- [x] Gestion des alertes : épisodes, gravité, **acquittement** depuis le dashboard
- [x] Notifications gratuites e-mail / SMS, alertes critiques seulement (engine/notify.py, docs/notifications.md)
- [x] Caméra du téléphone : page web, relais temps réel, détection de mouvement (camera/, api/routes/camera.py, engine/vision.py)
- [x] Mode simulation de repli, signalé « Simulé » au dashboard (scripts/fallback_sim.py)
- [x] Firmware ESP32 des deux nœuds (firmware/, compilé)
- [x] Scénarios d'intrusion TI-01..05 + rapport avant/après (attack-lab/)
- [x] Déploiement Docker/Windows (docker-compose, deploy/, lanceurs .bat) et réseau segmenté GNS3 (gns3/)
- [x] Dashboard protégé par mot de passe (session signée, anti force brute ; api/auth.py), caméra comprise
- [x] Notifications : état des canaux et envoi de test depuis le dashboard (page Moteur)
- [x] Configuration du firmware générée depuis `.env` et la CA du hub (plus de secrets.h à recopier)
- [x] Mesure des fausses alertes (scripts/false_alerts.py) ; résultats : docs/resultats_memoire.md


## Modèles de référence (amorçage à froid)

Télécharger les CSV de télémétrie TON_IoT dans `data/public/` (non versionnés), puis entraîner un modèle par catégorie :
```
python scripts/train_reference.py --category mouvement --csv data/public/IoT_Motion_Light.csv
python scripts/train_reference.py --category ouverture --csv data/public/IoT_Garage_Door.csv
python scripts/train_reference.py --category environnemental --csv data/public/IoT_Weather.csv
```
Chaque modèle est écrit dans `engine/models/reference/` avec ses métriques (.json). Sans modèle de référence pour une catégorie, le moteur apprend depuis zéro.

Par défaut, une référence ne lève pas d'alerte : elle empêche les fenêtres qu'elle juge anormales d'entrer dans la baseline
pendant l'amorçage, et la garde de compatibilité signale par un avis une référence abandonnée. `MYSA_REFERENCE_ALERTS=1`
rétablit ses alertes (essais de l'hypothèse H1). Justification chiffrée en tête de `engine/analyzer.py`.


## Comment le moteur décide

Pour chaque message reçu, le moteur relit la fenêtre des 20 derniers messages du même flux (appareil + capteur),
en calcule les caractéristiques, puis la soumet au modèle local du flux (ou, pendant l'amorçage, au modèle de référence
de sa catégorie). Le modèle local combine quatre détecteurs :

| Détecteur | Ce qu'il repère | Force de l'indice |
|---|---|---|
| Enveloppe de valeurs | pic, valeur hors domaine (SC-01) | fort : alerte immédiate, gravité high |
| Enveloppe de rythme | inondation de messages, ralentissement (SC-02) | fort |
| Tendance (pente de Theil-Sen sur 40 messages) | dérive progressive (SC-03), capteurs continus seulement | fort |
| Isolation Forest, seuil calibré sur l'entraînement | combinaison inhabituelle de caractéristiques | faible : 2 fenêtres suspectes sur 3, gravité medium |

Le chien de garde signale à part un flux devenu silencieux (SC-05). Les alertes d'un même flux sont regroupées en épisodes,
et `engine/risk.py` résume les épisodes récents de chaque appareil en un score de 0 à 100
(normal < 25 ≤ à surveiller < 60 ≤ critique). Une fenêtre suspecte, confirmée ou non, n'entre jamais dans la baseline.


## Évaluer le moteur sans broker

`scripts/replay_eval.py` rejoue les scénarios des appareils virtuels directement dans le moteur, avec une base et des modèles
temporaires (la base et les modèles du prototype ne sont pas touchés), en quelques secondes par scénario :
```
python scripts/replay_eval.py --seeds 1-5                    # sc00 à sc05, 5 graines
python scripts/replay_eval.py --presets sc00,sc03 --seeds 1-3 --out data/runs/replay.json
python scripts/replay_eval.py --no-reference                 # configuration « apprentissage depuis zéro »
```
Résultats (6 scénarios x 5 graines, vérité terrain des appareils virtuels, même règle de notation que `score_run.py`) :

| Scénario | Version initiale | Version actuelle |
|---|---|---|
| sc00 fonctionnement normal | 63 épisodes de fausse alerte | 0 |
| SC-01 valeurs aberrantes | 10/10 en 2 s (médiane), 56 épisodes faux | 10/10 en 2 s, 0 |
| SC-02 inondation | 5/5 en 62 s, 45 épisodes faux | 5/5 en 3 s, 1 |
| SC-03 dérive progressive | 5/5 en 38 s, 67 épisodes faux | 5/5 en 105 s, 1 |
| SC-04 attaque dès l'installation | 5/5 (*) | 0/5 : avis de la garde de compatibilité |
| SC-05 silence | 5/5 en 20 s | 5/5 en 20 s, 0 |

(*) Non significatif : la même référence « mouvement » signalait aussi le PIR virtuel en fonctionnement normal (sc00).
Ces résultats portent sur des générateurs simples choisis par nous ; ils ne remplacent pas les mesures sur le prototype physique.

Tests automatisés (base et modèles temporaires) :
```
pip install pytest httpx
python -m pytest tests
```
