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
import random
import time

import paho.mqtt.client as mqtt

HOST = "127.0.0.1"
PORT = 1883
DEVICE_ID = "esp32-sec-01"
TOPIC = f"home/{DEVICE_ID}/pir"


def publish(client, value):
    payload = {"device_id": DEVICE_ID, "sensor": "pir", "value": value, "unit": "bool"}
    client.publish(TOPIC, json.dumps(payload))


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(HOST, PORT)

    print("Publication de 25 messages 'normaux' (un par seconde)...")
    print("Regarde le terminal de 'python -m engine.ingest' : il doit afficher")
    print("la progression de la baseline (x/20 échantillons).")
    for _ in range(25):
        publish(client, random.choice([0, 1]))
        time.sleep(1)

    print("\nPublication d'un message 'anormal' (valeur hors norme pour un PIR)...")
    publish(client, 999)

    print("\nTerminé. Vérifie :")
    print("  - le terminal de l'ingestion : une ligne 'Comportement inhabituel détecté' ?")
    print("  - http://127.0.0.1:8000/api/alerts dans le navigateur")

    client.disconnect()


if __name__ == "__main__":
    main()
