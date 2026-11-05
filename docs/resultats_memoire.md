# Résultats pour le mémoire

Regroupe les mesures reproductibles produites par le prototype : fiabilité du moteur (avant/après),
tests d'intrusion, et captures du dashboard. Chaque résultat est **rejouable** avec le script indiqué.

> Les générateurs des appareils virtuels sont des modèles simples choisis par nous ; ces mesures
> éprouvent le moteur de façon reproductible et ne remplacent pas des relevés sur le prototype
> physique.

## 1. Fiabilité du moteur — fausses alertes (`scripts/false_alerts.py`)

Fonctionnement **normal** rejoué (1 jour simulé agrégé par configuration, 4 graines). Objectif du
mémoire : **moins d'une fausse alerte par jour**.

| Configuration | Épisodes de fausse alerte | Jours simulés | Fausses alertes / jour |
|---|---|---|---|
| **Avant** — références qui alertent (hypothèse H1) | 7 | 1,0 | **7,0** |
| **Après** — références en filtre seul (choix de Mysa) | 1 | 1,0 | **1,0** |

Lecture : le choix d'utiliser les modèles de référence comme **filtre de la baseline** (et non comme
détecteurs) divise les fausses alertes par **~7**. L'unique fausse alerte restante vient d'un flux
sans modèle de référence (débit caméra), qui apprend depuis zéro. Données : `data/runs/false_alerts.csv`.

## 2. Fiabilité du moteur — détection et fausses alertes par scénario (`scripts/replay_eval.py`)

6 scénarios × 5 graines, vérité terrain des appareils virtuels (voir aussi le tableau du `README`).

| Scénario | Version initiale | Version actuelle |
|---|---|---|
| sc00 fonctionnement normal | 63 épisodes de fausse alerte | 0 |
| SC-01 valeurs aberrantes | 10/10 en 2 s, 56 épisodes faux | 10/10 en 2 s, 0 |
| SC-02 inondation | 5/5 en 62 s, 45 épisodes faux | 5/5 en 3 s, 1 |
| SC-03 dérive progressive | 5/5 en 38 s, 67 épisodes faux | 5/5 en 105 s, 1 |
| SC-04 attaque dès l'installation | 5/5 (*) | 0/5 : avis de la garde de compatibilité |
| SC-05 silence | 5/5 en 20 s | 5/5 en 20 s, 0 |

Reproduire : `python scripts/replay_eval.py --seeds 1-5`.

## 3. Tests d'intrusion TI-01 à TI-05 (`attack-lab/run_report.py`)

Mesuré sur le hub durci (rapport complet : `attack-lab/report.example.md`).

| TI | Attaque | Avant (sans Mysa) | Après (Mysa) |
|----|---------|-------------------|--------------|
| TI-01 | Écoute du trafic MQTT | réussie (clair, anonyme) | 🛡️ **bloquée** (TLS + auth) |
| TI-02 | Force brute des identifiants | réussie (défauts) | 🛡️ **bloquée** (mot de passe résistant) |
| TI-03 | Usurpation / injection | réussie (ni ACL ni validation) | 🔎 **détectée ~0 s** (règle « valeur hors contrat ») + usurpation **bloquée par l'ACL** |
| TI-04 | Saturation | non détectée | ⚠️ détectée après apprentissage (cf. SC-02) ; non détectée à froid |
| TI-05 | Attaque de la caméra | flux accessible | contrôle par **segmentation réseau** (pare-feu GNS3) |

Défense en profondeur démontrée : chiffrement → authentification → ACL → règles → comportement →
segmentation. Reproduire depuis Kali : `python3 attack-lab/run_report.py`.

## 4. Captures du dashboard

Dans `docs/captures/` :

| Fichier | Vue |
|---|---|
| `1-maison.png` | Accueil : état de la maison, pièces, score de risque |
| `2-alertes.png` | Épisodes filtrables, gravité, acquittement |
| `3-appareil-chambre.png` | Détail d'un appareil : courbes, causes du score |
| `4-moteur.png` | État d'apprentissage de chaque flux |
| `5-telephone.png` | Page caméra du téléphone |

> À rafraîchir après la répétition pour montrer les ajouts récents (panneau de commandes de la
> maison, caméra en direct, badge « Simulé », acquittement des épisodes).

## 5. Tests automatisés

`python -m pytest tests` — **59 tests** au vert (moteur, règles, corrélation, API, acquittement,
notifications, caméra/vision, mode simulation).
