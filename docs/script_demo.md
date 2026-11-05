# Script de démonstration Mysa (≈ 15 min)

Scénario minuté pour la soutenance. Chaque étape indique **l'action**, **ce que montre le dashboard**
et **la réaction attendue de Mysa**. Prévoir l'apprentissage **la veille au soir** (laisser le hub et
les nœuds tourner toute la nuit) pour que les flux aient un modèle appris — sinon la détection
comportementale (rythme, dérive) n'est pas encore active.

> Avant de commencer : `deploy/mysa-reset-demo.ps1` **seulement** si l'on veut repartir d'une base
> vierge (on perd alors l'apprentissage de la nuit — à éviter juste avant la démo). Vérifier la
> checklist `docs/checklist_jour_j.md`.

| # | Temps | Action | Dashboard | Réaction attendue de Mysa |
|---|-------|--------|-----------|----------------------------|
| 1 | 0:00 | **Vie normale.** Présenter la maison au repos. | « Tout va bien », appareils en ligne, caméra en direct. | Aucun épisode ; flux « Surveillé » (modèle appris la nuit). |
| 2 | 1:30 | **Badge valide** : présenter un badge autorisé, la serrure s'ouvre (LED verte, 1 bip). Désarmer l'alarme. | Historique badge/serrure ; alarme « Désarmée ». | Accès normal, pas d'alerte. |
| 3 | 3:00 | **Badge refusé** : présenter un badge inconnu 5 fois (LED rouge, 2 bips ; au 5e, lecteur bloqué 30 s). | Photos dans *Passages de badge* ; compte à rebours « Lecteur bloqué ». | Refus isolés consignés sans alerte ; au 3e « accès refusés répétés » (moyenne), au 5e « lecteur bloqué » (**forte**, notifiée). |
| 4 | 4:30 | **Enrôler** le badge depuis le dashboard (« Autoriser ce badge »), re-présenter. | Commande envoyée ; badge accepté. | Le badge forgé devient autorisé → démontre la gestion des badges. |
| 5 | 6:00 | **Intrusion** : armer l'alarme, puis passer la main devant le PIR **sans badge**. | Épisode « forte » ; notification. | Corrélation **C-01** « mouvement sans accès, alarme armée », puis **C-02** « présence confirmée PIR + caméra ». Notification e-mail/SMS. |
| 6 | 8:00 | **Surchauffe** : approcher une source de chaleur du DHT22 (ou `fallback_sim`). | Courbe de température qui grimpe ; épisode « forte ». | Règle « surchauffe » (≥ 45 °C) + « variation brutale ». |
| 7 | 9:30 | **Nœud coupé** : débrancher un ESP32. | Appareil « hors ligne » ; score monte. | Présence (Last Will) → alerte « hors ligne » ; notification. |
| 8 | 10:30 | **Rebrancher** le nœud. | Repasse « en ligne ». | Grâce de reconnexion : pas de fausse alerte de rythme pendant 2 min. |
| 9 | 11:30 | **Attaque depuis Kali** : `python3 attack-lab/run_report.py`. | Nouvel épisode « valeur hors contrat ». | TI-01/02 **bloqués** (TLS/auth), TI-03 **détecté** ; montrer `attack-lab/report.md`. |
| 9 bis | 13:00 | **Accès au dashboard** : ouvrir le dashboard dans une fenêtre privée, taper 5 faux mots de passe. | Écran de connexion, puis « Trop d'essais ». | Sans session, ni l'API ni la caméra ne répondent ; la force brute est bloquée 5 min. |
| 10 | 13:30 | **Plan B / simulation** (si un nœud est HS) : `python scripts/fallback_sim.py --device esp32-cmf-01 --profile cmf`. | Badge **« Simulé »** sur l'appareil. | La démo continue avec des données crédibles, clairement signalées comme simulées. |
| 11 | 14:30 | **Acquitter** les épisodes depuis l'onglet Alertes. | Épisodes passent en « Acquittés ». | Clôture propre ; score redescend. |

## Commandes utiles pendant la démo

```bash
# Simuler une surchauffe sans source de chaleur réelle (étape 6)
python scripts/fallback_sim.py --device esp32-cmf-01 --profile cmf    # puis forcer une valeur chaude si besoin

# Plan B : remplacer un nœud défaillant (étape 10)
python scripts/fallback_sim.py --device esp32-sec-01 --profile sec

# Attaque (étape 9), depuis la VM Kali
set -a; source attack-lab/lab.env; set +a
python3 attack-lab/run_report.py --out attack-lab/report.md
```

## Replis prévus

- **Pas de réseau / matériel HS** : base de démonstration hors ligne — `python scripts/demo_seed.py`
  puis servir l'API sur `data/demo/mysa-demo.db` (voir `scripts/demo_seed.py`).
- **Un capteur HS** : `scripts/fallback_sim.py` (badge « Simulé » au dashboard).
- **Caméra indisponible** : la démo reste valable sans la caméra (le reste ne dépend pas d'elle).
