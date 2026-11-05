# Déploiement de Mysa sous Windows

Le hub complet (broker MQTT, moteur, API + dashboard, pont caméra) tourne dans **Docker** sur le PC
Windows. Les deux nœuds ESP32 se téléversent depuis le même PC. Tout se pilote par des fichiers
`.bat` à **double-cliquer** à la racine du projet.

## En bref

| Étape | Action | Une seule fois ? |
|---|---|---|
| 1 | Installer Docker Desktop, VS Code + PlatformIO, le pilote USB des ESP32 | oui |
| 2 | Copier le dossier du projet sur le PC | oui |
| 3 | Remplir `.env` (IP du PC, Wi-Fi, mots de passe) | oui |
| 4 | **Ouvrir pare-feu Mysa.bat** | oui |
| 5 | **Demarrer Mysa.bat** | à chaque démarrage du PC |
| 6 | **Televerser sec01.bat** puis **Televerser cmf01.bat** | après chaque changement de `.env` ou des certificats |
| 7 | **Verifier Mysa.bat**, puis ouvrir le dashboard | avant la démonstration |

---

## 1. Prérequis

1. **WSL2** : *PowerShell en administrateur* → `wsl --install`, puis redémarrer.
2. **Docker Desktop** : <https://www.docker.com/products/docker-desktop/>. Paramètres → General :
   cocher **« Use the WSL 2 based engine »** et **« Start Docker Desktop when you sign in »**.
3. **VS Code** (<https://code.visualstudio.com/>) + l'extension **PlatformIO IDE**. L'ouvrir une fois
   et attendre la fin de son installation : les scripts de téléversement utilisent son PlatformIO.
4. **Pilote USB des ESP32** : carte branchée, *Gestionnaire de périphériques → Ports (COM et LPT)*.
   Si la carte n'y apparaît pas en `COMx`, installer le pilote **CP210x** (Silicon Labs) ou **CH340**
   (WCH), selon la puce écrite près du port USB.

## 2. Copier le projet

Copier le dossier entier sur le PC (clé USB, zip). **Ne pas fusionner** avec une ancienne copie :
remplacer le dossier (une fusion mélange d'anciens scripts et des certificats de deux PC
différents, qui ne vont plus ensemble).

## 3. Remplir `.env` (une fois)

Le fichier `.env` à la racine contient tous les réglages ; s'il n'existe pas, copier `.env.example`.
Ouvrir avec `notepad .env` et vérifier :

| Variable | Valeur |
|---|---|
| `MYSA_HUB_IP` | IP de **ce PC** sur le Wi-Fi des nœuds (`ipconfig` → « Adresse IPv4 ») |
| `MYSA_WIFI_SSID`, `MYSA_WIFI_PASS` | Wi-Fi sur lequel se connectent les ESP32 (le même que le PC) |
| `MYSA_DASHBOARD_PASSWORD` | mot de passe demandé par le dashboard |
| `MQTT_PASSWORD`, `MYSA_CAM_PASSWORD`, `MYSA_SEC_PASSWORD`, `MYSA_CMF_PASSWORD` | comptes du broker (lettres, chiffres, `-`, `_`) |
| `MYSA_SMTP_*`, `MYSA_SMS_*` | canaux de notification (au moins un, voir §8) |

> **Attention à deux pièges.** Le Bloc-notes peut enregistrer le fichier sous le nom `.env.txt` (le
> script le signale). Et c'est `MYSA_HUB_IP` qui compte : `MQTT_HOST` ne sert qu'hors Docker.

Plus rien n'est à recopier ailleurs : le firmware lit lui-même `.env` et le certificat de la CA à la
compilation (`firmware/scripts/gen_config.py`). `firmware/include/secrets.h` n'existe plus.

**IP fixe** : donner au PC une réservation DHCP sur la box (recommandé). Si l'IP change, mettre à
jour `MYSA_HUB_IP`, relancer **Demarrer Mysa.bat** (il refait le certificat), puis retéléverser les
deux nœuds.

## 4. Pare-feu (une fois)

Double-clic sur **Ouvrir pare-feu Mysa.bat** et accepter la demande d'administrateur. Il ouvre les
ports **8000** (dashboard, caméra) et **8883** (MQTT TLS) sur le profil *Privé*, et propose de
passer le réseau en *Privé* s'il est classé *Public* : sinon les ports restent fermés.

## 5. Démarrer le hub

Docker Desktop lancé (« Engine running »), double-clic sur **Demarrer Mysa.bat**. Le script :

1. vérifie Docker, `.env` et que `MYSA_HUB_IP` est bien une adresse du PC ;
2. crée les **certificats** s'ils manquent, ou refait celui du hub si l'IP a changé (la CA est
   gardée) ;
3. crée ou met à jour les **comptes du broker** dès que les mots de passe de `.env` changent ;
4. construit et lance les trois services (`broker`, `engine`, `api`).

Le premier démarrage prend plusieurs minutes (téléchargement des images). Des lignes de Docker
peuvent s'afficher en rouge : c'est normal, le script ne s'arrête que sur une vraie erreur, avec
un message « Échec de… ».

À la fin : `== Hub Mysa démarré ==` et l'adresse du dashboard, `https://<MYSA_HUB_IP>:8000/dashboard/`.

## 6. Téléverser les nœuds ESP32

Une carte branchée en USB, double-clic sur **Televerser sec01.bat** (nœud sécurité : PIR, RFID,
serrure, buzzer, LED rouge et verte) ou **Televerser cmf01.bat** (nœud confort : DHT22, relais).
Le script liste les ports série et demande celui de la carte (débrancher l'autre carte en cas de
doute : le port qui disparaît est le sien). Il compile, téléverse, puis ouvre le moniteur série.

Attendu dans le moniteur :
```
=== Mysa esp32-sec-01 (securite & acces) ===
[WiFi] OK IP=192.168.x.y ...
[MQTT] Connexion TLS a <MYSA_HUB_IP>:8883 ... OK
[PUB] ok  home/esp32-sec-01/pir {...}
```

- `Connecting....____` qui s'éternise : maintenir le bouton **BOOT** de la carte.
- La première ligne indique le programme présent : elle doit correspondre à la carte (PIR sur
  sec-01, DHT22 sur cmf-01).
- Retéléverser les deux nœuds après tout changement de `.env` (Wi-Fi, IP, mots de passe) ou des
  certificats.

Comportement de sec-01 : badge accepté → serrure ouverte 5 s, **LED verte** et **1 bip** ; badge
refusé → **LED rouge** 2 s et **2 bips** ; 5 refus en 1 min → lecteur bloqué 30 s (3 bips, LED rouge
lente, temps restant affiché au dashboard). Chaque passage de badge est photographié si la caméra du
téléphone est active (page *Alertes* → *Passages de badge*). La LED rouge ne signale que les alertes.

Depuis VS Code, la même chose se fait par le panneau PlatformIO → *PROJECT TASKS* → `sec01` /
`cmf01` → *Upload* puis *Monitor* (dossier `firmware` ouvert).

## 7. Dashboard et caméra

- **Dashboard** : `https://<MYSA_HUB_IP>:8000/dashboard/`, mot de passe `MYSA_DASHBOARD_PASSWORD`.
  Accueil : état de la maison, commandes (porte, alarme et arrêt de la sirène, lampe, thermostat,
  enrôlement du dernier badge refusé), caméra en direct, journal. Pages *Alertes* (acquittement) et
  *Moteur* (apprentissage, notifications).
- **Certificat** : installer `broker\certs\ca.crt` sur le téléphone et sur le PC de présentation
  pour supprimer l'avertissement HTTPS (docs/https.md, section 3).
- **Caméra** : sur le téléphone, se connecter d'abord au dashboard, puis ouvrir
  `https://<MYSA_HUB_IP>:8000/camera/` et appuyer sur « Démarrer ».

## 8. Notifications

Renseigner au moins un canal dans `.env` (e-mail Gmail ou SMS par un téléphone Android :
docs/notifications.md), relancer **Demarrer Mysa.bat**, puis dashboard → **Moteur** →
**Envoyer une notification de test** : le résultat de chaque canal s'affiche.

Mysa notifie une fois par épisode, pour les alertes critiques seulement : alarme, intrusion, lecteur
de badges bloqué, surchauffe, nœud hors ligne.

## 9. Vérifier

Double-clic sur **Verifier Mysa.bat** : chaque point s'affiche `[OK]` ou `[!!]` avec la correction.
Il contrôle `.env`, Docker et les trois services, le certificat (signé, valable pour l'IP), les
ports 8883 et 8000 vus comme un ESP32 les voit, le pare-feu, la connexion des deux nœuds au broker
(30 dernières minutes) et les canaux de notification.

## Commandes utiles

| Action | Double-clic | Équivalent |
|---|---|---|
| Démarrer | Demarrer Mysa.bat | `deploy\mysa-start.ps1` |
| Arrêter (garde les données) | Arreter Mysa.bat | `deploy\mysa-stop.ps1` |
| Vérifier | Verifier Mysa.bat | `deploy\mysa-check.ps1` |
| Téléverser un nœud | Televerser sec01.bat / cmf01.bat | `deploy\mysa-flash.ps1 -Node sec01 -Port COM3` |
| Réinitialiser la base et les modèles | Reinitialiser demo Mysa.bat | `deploy\mysa-reset-demo.ps1` |
| État des services | | `docker compose ps` |
| Journaux | | `docker compose logs -f` (ou `logs broker`, `logs engine`) |

## Dépannage

| Symptôme | Cause et solution |
|---|---|
| « Docker Desktop ne répond pas » | Lancer Docker Desktop, attendre « Engine running ». |
| Lignes rouges `NativeCommandError` de Docker | Messages normaux de Docker affichés par PowerShell ; seul « Échec de… » est une erreur. |
| `MYSA_HUB_IP n'est pas une adresse de ce PC` | Corriger `.env` (`ipconfig`), relancer, retéléverser les nœuds. |
| Moniteur : `Connexion TLS a 192.168.x.y` avec une autre IP | Le nœud a été compilé avant le changement de `.env` : le retéléverser. |
| Moniteur : `errno 113` / `rc=-2` sans erreur X509 | Hub injoignable : pare-feu (§4), réseau *Public*, IP du hub, PC et nœuds sur le même Wi-Fi. |
| Moniteur : `X509 - Certificate verification failed` | Le nœud n'a pas la CA du hub : le retéléverser (la CA est relue à chaque compilation). Si cela persiste, **Verifier Mysa.bat**. |
| Moniteur : `rc=4` ou `rc=5` | Mot de passe refusé : relancer **Demarrer Mysa.bat** (comptes resynchronisés), puis retéléverser. |
| Moniteur : `[PUB] PLEIN` | Le nœud n'est pas connecté et sa file d'attente est pleine : voir les lignes ci-dessus. |
| Carte qui redémarre en boucle (`register dump`) | Programme d'une autre carte, ou câblage : lancer le test matériel (`deploy\mysa-flash.ps1 -Node hwtest_sec`). |
| Servo immobile (le test T3 échoue aussi) | Alimentation : 5 V externe sous charge, masse commune avec l'ESP32 ; une tension qui s'effondre sur la breadboard signale un court-circuit ou une alimentation trop faible. |
| Dashboard : « Mot de passe incorrect » puis « Trop d'essais » | 5 échecs bloquent 5 min (anti force brute) ; vérifier `MYSA_DASHBOARD_PASSWORD`. |
| Caméra : « connexion requise » | Se connecter au dashboard depuis le même téléphone, puis revenir sur `/camera/`. |
| Ports 8000 ou 8883 déjà pris | Un autre programme les utilise : `netstat -ano | findstr :8883`. |
| Repartir de zéro (certificats compris) | Arrêter, supprimer `broker\certs`, `broker\passwd`, relancer, retéléverser les deux nœuds. |
