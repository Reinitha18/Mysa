"""
Simule un appareil qui publie de la télémétrie "normale" pendant un moment,
puis un message franchement anormal — pour vérifier en quelques dizaines de
secondes que la boucle complète (baseline -> détection -> alerte) fonctionne,
sans avoir à republier des messages à la main avec mosquitto_pub.

Pré-requis : Mosquitto local lancé, et `python -m engine.ingest` lancé dans
un autre terminal (c'est lui qui va construire la baseline puis détecter
l'anomalie générée par ce script).

Usage : python scripts/simulate_device.py
"""

import json
import os
import random
import time

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()  # lit .env : mêmes réglages que le moteur (MQTT_HOST, MQTT_PORT, ...)

HOST = os.getenv("MQTT_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_PORT", "18830"))
USE_TLS = os.getenv("MQTT_USE_TLS", "false").lower() == "true"
CA_CERT = os.getenv("MQTT_CA_CERT") or None
USER = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASSWORD")
DEVICE_ID = "esp32-sec-01"
TOPIC = f"home/{DEVICE_ID}/pir"
N_NORMAL = 150
DELAY_S = 0.2


def publish(client, value):
    payload = {"device_id": DEVICE_ID, "sensor": "pir", "value": value, "unit": "bool"}
    client.publish(TOPIC, json.dumps(payload))


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if USER:
        client.username_pw_set(USER, PASSWORD)
    if USE_TLS:
        client.tls_set(ca_certs=CA_CERT)
    print(f"Connexion au broker {HOST}:{PORT} (TLS : {'oui' if USE_TLS else 'non'})")
    try:
        client.connect(HOST, PORT)
    except OSError as err:
        raise SystemExit(f"Connexion impossible à {HOST}:{PORT} ({err}). "
                         "Vérifie que Mosquitto tourne et que MQTT_HOST / MQTT_PORT sont corrects dans .env.")

    print(f"Publication de {N_NORMAL} messages 'normaux' (un toutes les {DELAY_S} s)...")
    print("Regarde le terminal de 'python -m engine.ingest' : il doit afficher")
    print("la progression de la baseline (x/20 échantillons) ; sans modèle de référence,")
    print("il faut une fenêtre de 20 messages puis ~100 messages pour 20 échantillons.")
    for _ in range(N_NORMAL):
        publish(client, random.choice([0, 1]))
        time.sleep(DELAY_S)

    print("\nPublication d'un message 'anormal' (valeur hors norme pour un PIR)...")
    publish(client, 999)

    print("\nTerminé. Vérifie :")
    print("  - le terminal de l'ingestion : une ligne 'Comportement inhabituel détecté' ?")
    print("  - http://127.0.0.1:8000/api/alerts dans le navigateur")

    client.disconnect()


if __name__ == "__main__":
    main()