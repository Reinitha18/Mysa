# firmware/scripts/gen_config.py -- script PlatformIO (extra_scripts = pre:...) des firmwares sec01/cmf01
#
# Génère include/mysa_config.h à chaque compilation, à partir de deux sources uniques du hub :
#   - ../.env               : Wi-Fi, IP du hub, mots de passe MQTT des nœuds ;
#   - ../broker/certs/ca.crt : la CA Mysa (créée par deploy/mysa-start.ps1 ou scripts/gen_certs.sh).
# Plus rien à recopier à la main : changer .env ou refaire les certificats, puis retéléverser.
# mysa_config.h contient des secrets : il est ignoré par .gitignore.
import os
import re

Import("env")  # noqa: F821 (fourni par PlatformIO/SCons)

PROJECT = env.subst("$PROJECT_DIR")  # noqa: F821
ROOT = os.path.dirname(PROJECT)
ENV_FILE = os.path.join(ROOT, ".env")
CA_FILE = os.path.join(ROOT, "broker", "certs", "ca.crt")
OUT = os.path.join(PROJECT, "include", "mysa_config.h")

REQUIRED = ["MYSA_WIFI_SSID", "MYSA_WIFI_PASS", "MYSA_HUB_IP", "MYSA_SEC_PASSWORD", "MYSA_CMF_PASSWORD"]


def fail(msg):
    print("\n*** Mysa : " + msg + "\n")
    env.Exit(1)  # noqa: F821


def read_dotenv(path):
    values = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
            if m:
                values[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return values


def c_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


if not os.path.isfile(ENV_FILE):
    fail(f"fichier {ENV_FILE} introuvable (copier .env.example en .env et le remplir).")
cfg = read_dotenv(ENV_FILE)
missing = [k for k in REQUIRED if not cfg.get(k) or cfg[k] == "change-me"]
if missing:
    fail("à renseigner dans .env : " + ", ".join(missing))
if not os.path.isfile(CA_FILE):
    fail(f"{CA_FILE} introuvable : démarrer le hub une première fois (deploy\\mysa-start.ps1), "
         "qui crée les certificats, puis recompiler.")
with open(CA_FILE, encoding="utf-8") as f:
    ca = f.read().strip()
if "BEGIN CERTIFICATE" not in ca:
    fail(f"{CA_FILE} n'est pas un certificat PEM.")

header = f"""// GÉNÉRÉ par firmware/scripts/gen_config.py depuis .env et broker/certs/ca.crt -- ne pas modifier.
#pragma once

#define WIFI_SSID   {c_string(cfg["MYSA_WIFI_SSID"])}
#define WIFI_PASS   {c_string(cfg["MYSA_WIFI_PASS"])}

#define MQTT_HOST   {c_string(cfg["MYSA_HUB_IP"])}   // IP du hub : figure dans son certificat
#define MQTT_PORT   8883

#if defined(DEVICE_SEC01)
  #define DEVICE_ID   "esp32-sec-01"
  #define MQTT_USER   "esp32-sec-01"
  #define MQTT_PASS   {c_string(cfg["MYSA_SEC_PASSWORD"])}
#elif defined(DEVICE_CMF01)
  #define DEVICE_ID   "esp32-cmf-01"
  #define MQTT_USER   "esp32-cmf-01"
  #define MQTT_PASS   {c_string(cfg["MYSA_CMF_PASSWORD"])}
#endif

// CA Mysa (broker/certs/ca.crt), PAS le certificat du serveur
static const char CA_CERT[] = R"PEM(
{ca}
)PEM";
"""

# Réécrit seulement si le contenu change, pour ne pas forcer une recompilation complète.
old = open(OUT, encoding="utf-8").read() if os.path.isfile(OUT) else None
if old != header:
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(header)
print(f"Mysa : configuration du nœud -> hub {cfg['MYSA_HUB_IP']}, Wi-Fi « {cfg['MYSA_WIFI_SSID']} »")
