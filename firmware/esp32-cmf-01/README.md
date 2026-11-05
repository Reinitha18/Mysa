# esp32-cmf-01 — nœud « confort »

Firmware PlatformIO **compilé** (chapitre 8.3 du mémoire). Code : `firmware/src/cmf01/main.cpp`.

## Capteurs et actionneurs

| Élément | Broche | Topic MQTT | Remarque |
|---|---|---|---|
| DHT22 | GPIO 4 | `home/esp32-cmf-01/temperature`, `/humidity` | publié toutes les 5 s |
| Relais (lampe / prise) | GPIO 27 | `home/esp32-cmf-01/relay` | **basse tension** pour la maquette |
| — lecture DHT en défaut | — | `home/esp32-cmf-01/dht_error` | câblage / pull-up |

États publiés (gardés en **NVS**) : `relay`, `relay_auto` (mode), `setpoint` (consigne °C).

## Logique embarquée

- **Thermostat local** : en mode `auto`, le relais s'enclenche au-dessus de la consigne et se coupe
  en dessous (hystérésis) ; en mode `manual`, le relais suit les commandes.
- Consigne par défaut 28 °C, bornée 10–40 °C, persistée en NVS.
- Réseau non bloquant, session MQTT persistante.

## Commandes acceptées (depuis le hub, `home/esp32-cmf-01/cmd/<act>`)

`relay` (on/off), `mode` (manual/auto), `setpoint` (10–40). Voir `api/routes/commands.py`.

## Compiler / flasher

```bash
cd firmware
pio run -e cmf01                                   # compiler
pio run -e cmf01 -t upload                         # flasher (upload_speed 115200 pour cette carte)
pio run -e hwtest_cmf -t upload                    # test matériel (DHT22), sans réseau
```

Wi-Fi, IP du hub et mot de passe MQTT du nœud sont lus dans `../.env`, et la CA dans
`../broker/certs/ca.crt`, à chaque compilation (`scripts/gen_config.py` → `include/mysa_config.h`, généré,
non versionné). Sous Windows : `Televerser cmf01.bat` à la racine du projet.
