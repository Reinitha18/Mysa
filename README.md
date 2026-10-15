# Mysa

Architecture autonome de cybersécurité comportementale pour les écosystèmes de maisons intelligentes.

Projet de fin d'études — voir le mémoire pour le détail de l'analyse, de la conception et des choix techniques.

## Structure du dépôt

```
mysa/
  engine/       -> moteur de détection comportementale (Python)
  api/          -> API FastAPI qui expose les données au dashboard
  broker/       -> configuration du broker MQTT (Mosquitto)
  firmware/     -> code embarqué des deux nœuds ESP32
  dashboard/    -> interface web de supervision (React) — à venir
  attack-lab/   -> scénarios du simulateur d'attaque — à venir
```

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

## Tester la boucle complète (baseline + détection)

Avec Mosquitto local lancé et `python -m engine.ingest` dans un terminal,
lance dans un autre terminal :
```
python scripts/simulate_device.py
```
Ce script publie 150 messages "normaux" (de quoi construire une baseline locale),
puis un message franchement anormal. Le terminal de l'ingestion doit afficher
la progression de l'apprentissage, puis une alerte sur le dernier message.
Vérifiable aussi via http://127.0.0.1:8000/api/alerts.

## État d'avancement

- [x] Moteur d'ingestion MQTT -> base de données locale
- [x] API de consultation (appareils, alertes)
- [x] Extraction de caractéristiques comportementales (engine/features.py)
- [x] Modèle de détection d'anomalies, baseline par appareil (engine/model.py)
- [x] Orchestration baseline -> détection -> alerte (engine/analyzer.py)
- [x] Catégories d'appareils et modèles de référence pour l'amorçage à froid (engine/categories.py, engine/reference.py, scripts/train_reference.py)
- [ ] Dashboard React
- [ ] Firmware ESP32
- [ ] Scénarios du simulateur d'attaque


## Modèles de référence (amorçage à froid)

Télécharger les CSV de télémétrie TON_IoT dans `data/public/` (non versionnés), puis entraîner un modèle par catégorie :
```
python scripts/train_reference.py --category mouvement --csv data/public/IoT_Motion_Light.csv
python scripts/train_reference.py --category ouverture --csv data/public/IoT_Garage_Door.csv
python scripts/train_reference.py --category environnemental --csv data/public/IoT_Weather.csv
```
Chaque modèle est écrit dans `engine/models/reference/` avec ses métriques (.json). Sans modèle de référence pour une catégorie, le moteur apprend depuis zéro.
