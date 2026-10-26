"""
Appareils virtuels de Mysa (VLAN 20) : plusieurs capteurs simulés qui publient en MQTT,
avec injection d'anomalies planifiées et enregistrement de la vérité terrain.

Appareils (catégorie Mysa entre parenthèses) :
  virt-hall-01     pir          détecteur de mouvement, périodes d'activité     (mouvement)
  virt-door-01     magnet       contact de porte, presque toujours fermée       (ouverture)
  virt-climate-01  temperature  dérive lente + bruit de 0,1 °C                  (environnemental)
                   humidity     humidité                                         (environnemental)
  virt-bulb-01     bulb_state   ampoule allumée / éteinte                        (aucune)
  virt-plug-01     plug_power   prise connectée, cycles d'un appareil (W)        (aucune)
  virt-cam-01      cam_bitrate  débit d'une caméra (kbit/s), lié au mouvement    (aucune)

Les générateurs sont des modèles SIMPLES choisis par nous : ils servent à éprouver le
moteur de façon reproductible (graine fixe), pas à représenter fidèlement un foyer réel.

Temps : les scénarios sont exprimés en secondes « virtuelles ». Avec --speed 5, 5 secondes
virtuelles s'écoulent par seconde réelle ; l'horodatage des messages reste en temps virtuel,
donc le moteur voit la cadence réelle d'un appareil (un message toutes les 2 s). Conséquence :
le chien de garde de silence n'est pertinent qu'avec --speed 1.

Exemples :
  python scripts/virtual_devices.py --preset sc00            # fonctionnement normal
  python scripts/virtual_devices.py --preset sc01            # valeurs aberrantes
  python scripts/virtual_devices.py --preset sc05            # silence (vitesse réelle)
  python scripts/virtual_devices.py --events mes_evenements.json --duration 900
  python scripts/virtual_devices.py --preset sc01 --dry-run  # affiche sans publier
"""

import argparse
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

DEVICES = {  # device_id -> [(capteur, unité, période en secondes virtuelles)]
    "virt-hall-01": [("pir", "bool", 2.0)],
    "virt-door-01": [("magnet", "bool", 2.0)],
    "virt-climate-01": [("temperature", "C", 3.0), ("humidity", "%", 3.0)],
    "virt-bulb-01": [("bulb_state", "bool", 5.0)],
    "virt-plug-01": [("plug_power", "W", 5.0)],
    "virt-cam-01": [("cam_bitrate", "kbps", 2.0)],
}

# Types d'événements : spike, stuck, flapping, offset, drift, flood, silence.
PRESETS = {
    "sc00": {"desc": "Fonctionnement normal, sans anomalie", "duration": 1100, "speed": 5, "events": []},
    "sc01": {"desc": "SC-01 valeurs aberrantes (pic de mouvement, pic de température)", "duration": 1100, "speed": 5,
             "events": [
                 {"t": 800, "device": "virt-hall-01", "sensor": "pir", "type": "spike", "value": 999},
                 {"t": 820, "device": "virt-climate-01", "sensor": "temperature", "type": "spike", "value": 40.0},
             ]},
    "sc02": {"desc": "SC-02 inondation de messages (rythme x20 pendant 60 s)", "duration": 1000, "speed": 5,
             "events": [{"t": 800, "device": "virt-hall-01", "sensor": "pir", "type": "flood",
                         "duration": 60, "factor": 20}]},
    "sc03": {"desc": "SC-03 dérive progressive de la température (+6 °C en 300 s)", "duration": 1200, "speed": 5,
             "events": [{"t": 800, "device": "virt-climate-01", "sensor": "temperature", "type": "drift",
                         "duration": 300, "delta": 6.0}]},
    "sc04": {"desc": "SC-04 appareil compromis dès l'installation (oscillation pendant 400 s)", "duration": 800,
             "speed": 5,
             "events": [{"t": 0, "device": "virt-hall-01", "sensor": "pir", "type": "flapping", "duration": 400}]},
    "sc05": {"desc": "SC-05 arrêt d'un appareil (silence de 90 s) — vitesse réelle", "duration": 200, "speed": 1,
             "events": [{"t": 60, "device": "virt-hall-01", "sensor": "pir", "type": "silence", "duration": 90}]},
}


class World:
    """État et générateurs de valeurs normales de tous les capteurs."""

    def __init__(self, rng):
        self.rng = rng
        self.pir = 0
        self.door, self.door_left = 0, 0
        self.walk = 0.0
        self.bulb = 0
        self.plug_until, self.plug_next = -1.0, rng.uniform(100, 300)

    def value(self, sensor: str, vt: float):
        r = self.rng
        if sensor == "pir":
            p01 = 0.03 + 0.02 * (0.5 + 0.5 * math.sin(2 * math.pi * vt / 900))  # activité qui varie un peu
            x = r.random()
            if self.pir == 0 and x < p01:
                self.pir = 1
            elif self.pir == 1 and x < 0.25:
                self.pir = 0
            return self.pir
        if sensor == "magnet":
            if self.door_left > 0:
                self.door_left -= 1
                self.door = 1 if self.door_left > 0 else 0
            elif r.random() < 0.004:
                self.door, self.door_left = 1, r.randint(5, 15)
            return self.door
        if sensor == "temperature":
            self.walk = max(-1.0, min(1.0, self.walk + r.gauss(0, 0.03)))
            return round(24 + 1.5 * math.sin(2 * math.pi * vt / 1800) + self.walk + r.gauss(0, 0.1), 1)
        if sensor == "humidity":
            return round(55 - 3 * math.sin(2 * math.pi * vt / 1800) + r.gauss(0, 0.4), 1)
        if sensor == "bulb_state":
            if r.random() < 0.01:
                self.bulb ^= 1
            return self.bulb
        if sensor == "plug_power":
            if vt >= self.plug_next and vt >= self.plug_until:
                self.plug_until = vt + r.uniform(60, 120)
                self.plug_next = vt + r.uniform(300, 600)
            return round((800 if vt < self.plug_until else 2) * (1 + r.gauss(0, 0.02)), 1)
        if sensor == "cam_bitrate":
            return round(1500 + 800 * self.pir + r.gauss(0, 60), 0)
        raise ValueError(f"capteur inconnu : {sensor}")


def active(events, device, sensor, vt, period):
    """Événements actifs pour ce flux à l'instant virtuel vt."""
    out = []
    for e in events:
        if e["device"] == device and e["sensor"] == sensor:
            end = e["t"] + max(e.get("duration", 0), period * 0.99)
            if e["t"] <= vt < end:
                out.append(e)
    return out


def distort(e, value, vt, state):
    """Applique une anomalie à une valeur normale."""
    kind = e["type"]
    if kind == "spike":
        return e.get("value", 999)
    if kind == "stuck":
        return state.setdefault(("held", e["t"]), value)
    if kind == "flapping":
        state["flip"] = state.get("flip", 0) ^ 1
        return e.get("high", 1) if state["flip"] else e.get("low", 0)
    if kind == "offset":
        return round(value + e["delta"], 2)
    if kind == "drift":
        return round(value + e["delta"] * (vt - e["t"]) / max(e["duration"], 1), 2)
    return value  # flood : rythme modifié par l'ordonnanceur ; silence : pas de publication


def run(emit, events, duration, speed, seed=1, devices=None, realtime=True, start_wall=None):
    """Boucle de simulation. emit(topic, payload_dict) publie un message."""
    rng = random.Random(seed)
    world = World(rng)
    start_wall = start_wall or datetime.now(timezone.utc)
    streams = []
    for dev, sensors in DEVICES.items():
        if devices and dev not in devices:
            continue
        for sensor, unit, period in sensors:
            streams.append({"device": dev, "sensor": sensor, "unit": unit, "period": period,
                            "next": rng.uniform(0, period), "state": {}, "last": None})
    t_real0 = time.perf_counter()
    sent = 0
    while streams:
        s = min(streams, key=lambda x: x["next"])
        vt = s["next"]
        if vt > duration:
            break
        if realtime:
            delay = vt / speed - (time.perf_counter() - t_real0)
            if delay > 0:
                time.sleep(delay)
        evs = active(events, s["device"], s["sensor"], vt, s["period"])
        types = {e["type"] for e in evs}
        period = s["period"]
        if "silence" in types:
            s["next"] += period
            continue
        if "flood" in types and s["last"] is not None:
            value = s["last"]  # même valeur, envoyée beaucoup plus vite
            period = period / max(evs[0].get("factor", 20), 1)
        else:
            value = world.value(s["sensor"], vt)
            s["last"] = value
            for e in evs:
                value = distort(e, value, vt, s["state"])
        ts = (start_wall + timedelta(seconds=vt)).isoformat()
        emit(f"home/{s['device']}/{s['sensor']}",
             {"device_id": s["device"], "sensor": s["sensor"], "value": value, "unit": s["unit"], "ts": ts})
        sent += 1
        s["next"] += period
    return sent


def ground_truth(events, start_wall):
    """Vérité terrain : fenêtre de chaque anomalie en temps virtuel et en horodatage."""
    out = []
    for e in events:
        end = e["t"] + e.get("duration", 0)
        out.append({**e, "start_ts": (start_wall + timedelta(seconds=e["t"])).isoformat(),
                    "end_ts": (start_wall + timedelta(seconds=end)).isoformat()})
    return out


def mqtt_emitter():
    import paho.mqtt.client as mqtt
    from dotenv import load_dotenv
    load_dotenv()
    host = os.getenv("MQTT_HOST", "127.0.0.1")
    port = int(os.getenv("MQTT_PORT", "1883"))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if os.getenv("MQTT_USER"):
        client.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASSWORD"))
    if os.getenv("MQTT_USE_TLS", "false").lower() == "true":
        client.tls_set(ca_certs=os.getenv("MQTT_CA_CERT") or None)
    print(f"Connexion au broker {host}:{port}")
    try:
        client.connect(host, port)
    except OSError as err:
        raise SystemExit(f"Connexion impossible à {host}:{port} ({err}). Vérifie Mosquitto et .env.")
    client.loop_start()

    def emit(topic, payload):
        client.publish(topic, json.dumps(payload))

    return emit, client


def main():
    ap = argparse.ArgumentParser(description="Appareils virtuels Mysa")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="scénario prédéfini")
    ap.add_argument("--events", help="fichier JSON d'événements personnalisés (liste)")
    ap.add_argument("--duration", type=float, help="durée en secondes virtuelles")
    ap.add_argument("--speed", type=float, help="facteur d'accélération du temps")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--devices", help="liste d'appareils séparés par des virgules")
    ap.add_argument("--events-out", default="data/runs/last_events.json", help="vérité terrain écrite ici")
    ap.add_argument("--dry-run", action="store_true", help="affiche les messages au lieu de les publier")
    args = ap.parse_args()

    preset = PRESETS[args.preset] if args.preset else {"desc": "personnalisé", "duration": 1100, "speed": 5, "events": []}
    events = list(preset["events"])
    if args.events:
        with open(args.events, encoding="utf-8") as fh:
            events = json.load(fh)
    duration = args.duration or preset["duration"]
    speed = args.speed or preset["speed"]
    devices = set(args.devices.split(",")) if args.devices else None
    if any(e["type"] == "silence" for e in events) and speed != 1:
        print("Attention : le chien de garde de silence n'est pertinent qu'avec --speed 1.", file=sys.stderr)

    start_wall = datetime.now(timezone.utc)
    os.makedirs(os.path.dirname(args.events_out) or ".", exist_ok=True)
    with open(args.events_out, "w", encoding="utf-8") as fh:
        json.dump({"preset": args.preset, "seed": args.seed, "duration": duration, "speed": speed,
                   "start_wall": start_wall.isoformat(), "events": ground_truth(events, start_wall)},
                  fh, indent=2, ensure_ascii=False)
    print(f"{preset['desc']} — {duration:.0f} s virtuelles à la vitesse x{speed:g} "
          f"(~{duration / speed:.0f} s réelles). Vérité terrain : {args.events_out}")

    if args.dry_run:
        emit, client = (lambda topic, p: print(json.dumps(p, ensure_ascii=False))), None
        realtime = False
    else:
        emit, client = mqtt_emitter()
        realtime = True
    sent = run(emit, events, duration, speed, seed=args.seed, devices=devices, realtime=realtime,
               start_wall=start_wall)
    if client:
        time.sleep(0.5)
        client.loop_stop()
        client.disconnect()
    print(f"Terminé : {sent} messages publiés.")


if __name__ == "__main__":
    main()
