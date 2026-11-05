# esp32-sec-01 — nœud « sécurité & accès »

Firmware PlatformIO **compilé** (chapitre 8.3 du mémoire). Code : `firmware/src/sec01/main.cpp`.

## Capteurs et actionneurs

| Élément | Broche | Topic MQTT | Remarque |
|---|---|---|---|
| PIR HC-SR501 | GPIO 13 | `home/esp32-sec-01/pir` | mouvement, publié toutes les 2 s |
| Lecteur RFID RC522 | SS=5, RST=22 (SPI) | `home/esp32-sec-01/rfid` | `1` autorisé / `0` refusé, UID en méta |
| Serrure (servo SG90) | GPIO 27 | `home/esp32-sec-01/lock` | **alimentation 5 V séparée**, masse commune |
| Buzzer actif | GPIO 25 | `home/esp32-sec-01/alarm` | alarme locale |
| LED rouge | GPIO 26 | — | alertes seulement : clignote vite en alarme, fixe 2 s après un badge refusé (+ 2 bips), lente pendant le blocage du lecteur |
| LED verte | GPIO 21 | — | allumée tant que la serrure est ouverte ; badge accepté = 1 bip |
| Contact de porte MC-38 | GPIO 14 | `home/esp32-sec-01/door` | désactivé par défaut (`DOOR_ENABLED`) |

États publiés à chaque (re)connexion : `arm`, `lock`, `alarm`, `badges` (compteur), `rfid_lockout`.

## Logique embarquée

- **Alarme locale** avec délai de sortie ; se déclenche sur mouvement/accès non autorisé quand armée.
- **Anti force brute** : 5 badges refusés en 1 min → lecteur **bloqué 30 s** ; `rfid_lockout` publie la
  durée du blocage en secondes (`0` à la fin), le dashboard affiche le temps restant.
- **Badges** stockés en **NVS**, gérés à distance (`badge_add` / `badge_del`, UID).

## Commandes acceptées (depuis le hub, `home/esp32-sec-01/cmd/<act>`)

`lock` (open/close), `arm` (on/off), `alarm` (off), `buzzer` (on/off), `led` (on/off),
`badge_add` / `badge_del` (UID). Voir `api/routes/commands.py`.

## Compiler / flasher

```bash
cd firmware
pio run -e sec01                                   # compiler
pio run -e sec01 -t upload                         # flasher (adapter le port COM)
pio run -e hwtest_sec -t upload                    # test matériel (RFID relu en continu), sans réseau
```

Wi-Fi, IP du hub et mot de passe MQTT du nœud sont lus dans `../.env`, et la CA dans
`../broker/certs/ca.crt`, à chaque compilation (`scripts/gen_config.py` → `include/mysa_config.h`, généré,
non versionné). Sous Windows : `Televerser sec01.bat` à la racine du projet.

> Câblage matériel restant (toi) : corriger le lecteur RC522 (répond `0x00`) et monter le servo.
