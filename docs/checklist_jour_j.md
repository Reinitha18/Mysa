# Liste de vérification — jour J

À dérouler avant la soutenance. Cocher chaque point.

## La veille au soir

- [ ] Hub démarré (**Demarrer Mysa.bat**) et nœuds ESP32 connectés.
- [ ] **Verifier Mysa.bat** : aucun `[!!]`.
- [ ] **Apprentissage de nuit** : laisser tourner le hub + les nœuds toute la nuit pour que chaque
      flux ait un modèle local appris (sinon pas de détection de rythme/dérive).
- [ ] Caméra testée depuis le téléphone (`https://<hub>:8000/camera/`), flux visible au dashboard.
- [ ] Notifications testées (un canal au moins) : dashboard → **Moteur** → « Envoyer une notification de test ».

## Matériel

- [ ] Planche de maquette montée (voir `docs/plan_maquette.md`), composants fixés.
- [ ] Nœud sec-01 : PIR, RFID (lecteur corrigé), serrure servo, buzzer, LED rouge (GPIO 26) et verte (GPIO 21).
- [ ] Nœud cmf-01 : DHT22, relais lampe/prise (basse tension).
- [ ] Téléphone-caméra sur support, chargé.
- [ ] Badges : au moins un **autorisé** et un **inconnu** (pour l'étape « badge refusé »).
- [ ] Source de chaleur douce pour la surchauffe (ou prévoir `fallback_sim`).

## Alimentation

- [ ] Deux alimentations 5 V (une par nœud), servo sur sortie dédiée.
- [ ] Multiprise unique accessible (coupure rapide).
- [ ] Téléphone et poste de démonstration chargés / branchés.

## Réseau

- [ ] Hub en **IP fixe** (`MYSA_HUB_IP`), joignable depuis le poste de démo.
- [ ] Pare-feu Windows : ports 8000 et 8883 ouverts, réseau en *Privé* (**Ouvrir pare-feu Mysa.bat**).
- [ ] ESP32 et téléphone sur le bon réseau (VLAN 20 / box des objets).
- [ ] Certificat `ca.crt` installé sur le téléphone (pas d'avertissement HTTPS).
- [ ] (Si lab) GNS3 lancé, OpenWrt et VM en marche ; VM Kali prête (attaque étape 9).

## Comptes et clés

- [ ] `.env` renseigné (mots de passe broker, pas « change-me », Wi-Fi des nœuds).
- [ ] Mot de passe du dashboard (`MYSA_DASHBOARD_PASSWORD`) connu ; session ouverte sur le PC de présentation **et** le téléphone-caméra.
- [ ] Mot de passe d'application Gmail valide (notifications e-mail).
- [ ] E-mail et/ou passerelle SMS configurés (si démontrés).
- [ ] `attack-lab/lab.env` prêt sur la VM Kali (cible, CA, identifiants).

## Plan B (replis)

- [ ] `deploy/mysa-reset-demo.ps1` connu (remise à zéro — **pas** juste avant la démo).
- [ ] `scripts/fallback_sim.py` testé (badge « Simulé » visible) pour remplacer un nœud HS.
- [ ] Base de démonstration hors ligne prête : `python scripts/demo_seed.py` + API sur
      `data/demo/mysa-demo.db` (plan B total sans réseau ni matériel).
- [ ] Captures d'écran du dashboard en réserve (au cas où tout tombe).

## Juste avant de commencer

- [ ] Dashboard ouvert et connecté sur l'écran de présentation (`https://<hub>:8000/dashboard/`).
- [ ] Onglet Alertes vide ou acquitté (état propre).
- [ ] Minuteur / script `docs/script_demo.md` sous les yeux.
