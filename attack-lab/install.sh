#!/usr/bin/env bash
# Installe le lab d'attaque Mysa sur la VM Kali : outils d'intrusion + dépendances Python.
# À lancer dans la VM Kali (réseau de laboratoire isolé) :  bash attack-lab/install.sh
#
# ⚠️ À utiliser uniquement contre le prototype Mysa, dont tu es propriétaire. Voir README.md.
set -euo pipefail

echo "== Lab d'attaque Mysa : installation =="

if command -v apt-get >/dev/null 2>&1; then
  echo "-> Paquets système (nmap, mosquitto-clients, hydra)…"
  sudo apt-get update -y
  sudo apt-get install -y nmap mosquitto-clients hydra python3-pip python3-venv
else
  echo "   (apt introuvable : installe manuellement nmap, mosquitto-clients, hydra)"
fi

echo "-> Dépendances Python (paho-mqtt, websocket-client)…"
if pip3 install --help 2>/dev/null | grep -q break-system-packages; then
  pip3 install --break-system-packages --user paho-mqtt websocket-client
else
  pip3 install --user paho-mqtt websocket-client
fi

echo "-> Fichier de configuration du lab…"
cd "$(dirname "$0")"
if [[ ! -f lab.env ]]; then
  cp lab.env.example lab.env
  echo "   lab.env créé depuis lab.env.example — ajuste TARGET_HOST, les identifiants, le CA."
else
  echo "   lab.env déjà présent."
fi

cat <<'EOF'

Installation terminée.

Avant de lancer les scénarios :
  1) Copier le certificat de la CA Mysa (broker/certs/ca.crt du hub) sur la VM Kali,
     et renseigner CA_CERT dans attack-lab/lab.env.
  2) Ajuster TARGET_HOST (IP du hub) et, pour les scénarios authentifiés, STOLEN_USER /
     STOLEN_PASSWORD (identifiants d'un nœud supposé compromis).
  3) Charger la config :   set -a; source attack-lab/lab.env; set +a

Lancer le rapport complet :
  python3 attack-lab/run_report.py --out attack-lab/report.md

Ou un scénario isolé :
  python3 attack-lab/scenarios/ti03_usurpation.py
EOF
