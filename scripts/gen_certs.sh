#!/usr/bin/env bash
# Génère l'autorité de certification (CA) privée de Mysa et un certificat serveur « mysa-hub ».
# Le même certificat sert au broker MQTT (TLS 8883) ET au hub HTTPS (API + page caméra), car
# l'accès à la caméra dans Chrome impose HTTPS (voir docs/https.md).
#
# Un seul CA à installer sur le téléphone et les postes : il signe tout le reste.
# La clé de la CA (ca.key) et la clé serveur (server.key) ne sont jamais committées (.gitignore).
#
# Usage :
#   scripts/gen_certs.sh [ADRESSE_IP_DU_HUB] [NOM_DNS]
#   ADRESSE_IP_DU_HUB : IP du hub sur le réseau (défaut 192.168.50.20)
#   NOM_DNS           : nom d'hôte (défaut mysa-hub)
#
# Les fichiers sont écrits dans broker/certs/ :
#   ca.crt / ca.key           autorité de certification Mysa
#   server.crt / server.key   certificat du hub (SAN : NOM_DNS + localhost + IP)
set -euo pipefail

HUB_IP="${1:-192.168.50.20}"
HUB_DNS="${2:-mysa-hub}"
DIR="$(cd "$(dirname "$0")/.." && pwd)/broker/certs"
DAYS_CA=3650
DAYS_SRV=825   # <= 825 jours : limite acceptée par les navigateurs et Android récents

mkdir -p "$DIR"
cd "$DIR"

echo "→ Dossier : $DIR"
echo "→ Hub : DNS=$HUB_DNS, IP=$HUB_IP"

# 1) Autorité de certification (créée une seule fois ; réutilisée si déjà présente)
if [[ -f ca.key && -f ca.crt ]]; then
  echo "→ CA déjà présente : réutilisation de ca.crt / ca.key"
else
  echo "→ Création de la CA Mysa"
  openssl genrsa -out ca.key 4096
  openssl req -x509 -new -nodes -key ca.key -sha256 -days "$DAYS_CA" \
    -subj "/C=MG/O=Mysa/CN=Mysa Root CA" -out ca.crt
fi

# 2) Certificat serveur signé par la CA, avec SAN (nom + IP indispensables aux navigateurs)
echo "→ Création du certificat serveur ($HUB_DNS / $HUB_IP)"
openssl genrsa -out server.key 2048
openssl req -new -key server.key -subj "/C=MG/O=Mysa/CN=$HUB_DNS" -out server.csr

# L'IP figure aussi en « DNS: » : mbedTLS 2.x (cœur Arduino ESP32 2.x) ne compare le nom demandé
# qu'aux entrées DNS du SAN ; sans elle, un nœud qui se connecte par IP peut refuser le certificat.
cat > server.ext <<EOF
subjectAltName = DNS:$HUB_DNS, DNS:broker, DNS:localhost, DNS:$HUB_IP, IP:$HUB_IP, IP:127.0.0.1
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
EOF

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days "$DAYS_SRV" -sha256 -extfile server.ext
rm -f server.csr server.ext

# ca.key reste secret (il signe les certificats, le broker ne le lit jamais).
# server.key / server.crt / ca.crt doivent être lisibles par l'utilisateur « mosquitto » du
# conteneur (uid 1883) : lecture seule pour tous, écriture pour personne (mosquitto refuse un
# fichier accessible en écriture par le groupe/les autres, pas en lecture).
chmod 600 ca.key 2>/dev/null || true
chmod 644 server.key server.crt ca.crt 2>/dev/null || true
echo
echo "✓ Terminé. Fichiers dans $DIR :"
ls -1 ca.crt ca.key server.crt server.key
echo
echo "Empreinte du certificat serveur :"
openssl x509 -in server.crt -noout -fingerprint -sha256
echo
echo "Prochaines étapes : voir docs/https.md (lancer le hub en HTTPS, installer ca.crt sur le téléphone)."
