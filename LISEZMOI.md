# Mysa — correctif étape 2 (backend)

Copier tout le contenu par-dessus le dépôt (remplacer les fichiers existants).
Ne contient AUCUN modèle : tes modèles de référence (engine/models/reference/) restent intacts.

Nouveaux : engine/watchdog.py, api/routes/episodes.py, api/routes/streams.py
Modifiés : engine/storage.py, engine/analyzer.py, engine/ingest.py, api/main.py, api/routes/alerts.py
(+ les fichiers des correctifs précédents, déjà appliqués : catégories, références, scripts)

Base de données : une base existante est migrée automatiquement au démarrage (colonnes ajoutées à alerts,
tables episodes et streams). Aucune suppression nécessaire.
