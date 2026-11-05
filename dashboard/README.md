# Dashboard Mysa

Interface de supervision (React + Vite + Recharts, chapitre 6.1.6 du mémoire), aux couleurs du logo.
Elle consomme l'API (`/api/devices`, `/api/streams`, `/api/episodes`, `/api/alerts`, `/api/commands`)
et le flux temps réel `/ws/alerts`.

| Page | Pour qui | Contenu |
|---|---|---|
| Maison | l'occupant | état de la maison sous le toit du logo (bleu, ambre ou rouge), une « pièce » par appareil avec ses dernières mesures et son score de risque, journal des épisodes en phrases simples |
| Alertes | l'analyste | épisodes filtrables (anomalies, silences, avis, appareil), détecteur, gravité, durée ; chaque épisode se déplie sur ses alertes brutes |
| Appareil | les deux | score de risque et ses causes, une courbe par capteur avec les épisodes surlignés, étape d'apprentissage, commandes des actionneurs (nœuds ESP32) |
| Moteur | le jury, l'analyste | étape d'apprentissage de chaque flux, référence, cadence, et ce qui déclenche une alerte |

Une notification apparaît à chaque nouvel épisode (WebSocket). La couleur d'un état est toujours doublée d'un libellé.
Les polices sont embarquées (paquets @fontsource) : aucune connexion Internet n'est nécessaire, même dans le VLAN 30.

## Développement

```
cd dashboard
npm install
npm run dev          # http://localhost:5173 (l'API doit tourner sur le port 8000)
```
Le serveur de développement relaie `/api` et `/ws` vers l'API : pas de configuration CORS supplémentaire.

## Démonstration (un seul processus)

```
cd dashboard && npm run build && cd ..
uvicorn api.main:app        # dashboard sur http://127.0.0.1:8000/dashboard/
```

Sans broker ni appareils (plan B de soutenance), une base de démonstration réaliste :
```
python scripts/demo_seed.py
# Windows : $env:DB_PATH="data/demo/mysa-demo.db"; uvicorn api.main:app
# Linux   : DB_PATH=data/demo/mysa-demo.db uvicorn api.main:app
```
Les données de démonstration se terminent au moment où le script est lancé : le relancer juste avant la présentation.

Les noms de pièces affichés (Entrée, Salon, Chambre…) se règlent dans `src/labels.js`.
