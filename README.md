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

## État d'avancement

- [x] Moteur d'ingestion MQTT -> base de données locale
- [x] API de consultation (appareils, alertes)
- [ ] Extraction de caractéristiques comportementales (engine/features.py — squelette à compléter)
- [ ] Modèle de détection d'anomalies (engine/model.py — squelette à compléter)
- [ ] Dashboard React
- [ ] Firmware ESP32
- [ ] Scénarios du simulateur d'attaque
