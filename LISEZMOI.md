# Mysa — lisez-moi d'abord

Prototype de maison intelligente sécurisée : deux nœuds ESP32 (sécurité, confort), une caméra
(téléphone), et un hub qui apprend le comportement normal de chaque capteur, détecte les anomalies,
alerte et notifie. Le hub tourne dans Docker sur un PC Windows.

## Démarrer sous Windows

1. **Une fois** : installer Docker Desktop et VS Code + PlatformIO, remplir `.env`, double-cliquer
   **Ouvrir pare-feu Mysa.bat** (détails : `docs/deploiement_windows.md`, §1 à §4).
2. **Demarrer Mysa.bat** : lance le broker, le moteur et le dashboard (crée les certificats au
   premier démarrage).
3. **Televerser sec01.bat** puis **Televerser cmf01.bat**, chaque carte branchée en USB.
4. **Verifier Mysa.bat** : tout doit être `[OK]`.
5. Ouvrir `https://<MYSA_HUB_IP>:8000/dashboard/` (mot de passe : `MYSA_DASHBOARD_PASSWORD` dans `.env`).

## Où trouver quoi

| Besoin | Document |
|---|---|
| Déploiement pas à pas et dépannage | `docs/deploiement_windows.md` |
| Préparer la soutenance | `docs/checklist_jour_j.md`, puis `docs/script_demo.md` |
| Câblage des nœuds | `docs/Mysa_guide_cablage_maquette.pdf` (+ LED verte de sec-01 sur GPIO 21) |
| Notifications (e-mail, SMS) | `docs/notifications.md` |
| Certificat sur le téléphone (caméra) | `docs/https.md` |
| Architecture, moteur, état d'avancement | `README.md` |
| Scénarios d'attaque (Kali) | `attack-lab/README.md` |

`.env` et `broker/` contiennent des secrets (mots de passe, clé de la CA) : ne pas les publier.
