"""
Mode SIMULATION de repli (mémoire, chapitre 8). Si un composant physique tombe en panne le jour de
la démonstration, ce script fait publier à sa place des mesures réalistes, en se faisant passer pour
le vrai appareil (mêmes topics, mêmes identifiants → conforme à l'ACL du broker), et pose un drapeau
RETENU home/<id>/sim = 1 pour que le dashboard affiche clairement « Simulé ». À l'arrêt, il repose
le drapeau à 0.

Les valeurs proviennent des générateurs des appareils virtuels (scripts/virtual_devices.World) :
des modèles simples, suffisants pour une démonstration crédible.

Exemples :
  # le nœud confort est tombé : on le simule
  python scripts/fallback_sim.py --device esp32-cmf-01 --profile cmf
  # le nœud sécurité (détecteur de mouvement)
  python scripts/fallback_sim.py --device esp32-sec-01 --profile sec

Identifiants : par défaut, l'utilisateur MQTT = le device_id, mot de passe via --password ou la
variable d'environnement SIM_PASSWORD (sinon MQTT_PASSWORD). Broker : variables MQTT_* du .env.
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from virtual_devices import World  # noqa: E402

load_dotenv()

# Profils : quels capteurs simuler pour chaque type de nœud (capteur, unité, période en secondes).
PROFILES = {
    "sec": [("pir", "bool", 2.0)],
    "cmf": [("temperature", "C", 3.0), ("humidity", "%", 3.0)],
    "climate": [("temperature", "C", 3.0), ("humidity", "%", 3.0)],
}


def build_client(device_id: str, user: str, password: str) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"mysa-sim-{device_id}")
    c.username_pw_set(user, password)
    if os.getenv("MQTT_USE_TLS", "true").lower() == "true":
        c.tls_set(ca_certs=os.getenv("MQTT_CA_CERT") or None)
    # Last Will : si le simulateur disparaît, le nœud est marqué hors ligne.
    c.will_set(f"home/{device_id}/status", "offline", qos=1, retain=True)
    return c


def main():
    ap = argparse.ArgumentParser(description="Simulateur de repli d'un nœud Mysa")
    ap.add_argument("--device", required=True, help="device_id du nœud à simuler (ex. esp32-cmf-01)")
    ap.add_argument("--profile", choices=sorted(PROFILES), help="jeu de capteurs à simuler")
    ap.add_argument("--duration", type=float, default=0, help="durée en secondes (0 = sans fin)")
    ap.add_argument("--speed", type=float, default=1.0, help="facteur d'accélération du temps")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--user", default=None, help="utilisateur MQTT (défaut : le device_id)")
    ap.add_argument("--password", default=None, help="mot de passe MQTT (défaut : SIM_PASSWORD/MQTT_PASSWORD)")
    args = ap.parse_args()

    sensors = PROFILES[args.profile] if args.profile else PROFILES["cmf"]
    user = args.user or args.device
    password = args.password or os.getenv("SIM_PASSWORD") or os.getenv("MQTT_PASSWORD")
    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "8883"))

    client = build_client(args.device, user, password)
    client.connect(host, port, keepalive=30)
    client.loop_start()
    # Présence + drapeau « simulé » (retenus, pour que le dashboard les voie à la connexion).
    client.publish(f"home/{args.device}/status", "online", qos=1, retain=True)
    client.publish(f"home/{args.device}/sim", "1", qos=1, retain=True)
    print(f"Simulation de {args.device} ({', '.join(s for s, _, _ in sensors)}) vers {host}:{port}. "
          "Ctrl+C pour arrêter.")

    rng = random.Random(args.seed)
    world = World(rng)
    streams = [{"sensor": s, "unit": u, "period": p, "next": rng.uniform(0, p)} for s, u, p in sensors]
    start = time.perf_counter()
    sent = 0
    try:
        while True:
            s = min(streams, key=lambda x: x["next"])
            vt = s["next"]
            if args.duration and vt > args.duration:
                break
            delay = vt / args.speed - (time.perf_counter() - start)
            if delay > 0:
                time.sleep(delay)
            value = world.value(s["sensor"], vt)
            ts = datetime.now(timezone.utc).isoformat()
            client.publish(f"home/{args.device}/{s['sensor']}",
                           json.dumps({"device_id": args.device, "sensor": s["sensor"],
                                       "value": value, "unit": s["unit"], "ts": ts}), qos=1)
            sent += 1
            if sent % 20 == 0:
                print(f"  {sent} messages simulés…", end="\r", flush=True)
            s["next"] += s["period"]
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(f"home/{args.device}/sim", "0", qos=1, retain=True)  # fin de la simulation
        time.sleep(0.3)
        client.loop_stop()
        client.disconnect()
        print(f"\nSimulation arrêtée ({sent} messages). Drapeau « simulé » retiré.")


if __name__ == "__main__":
    main()
