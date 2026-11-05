"""
Remplit une base de DÉMONSTRATION pour le dashboard, sans broker : les appareils virtuels
(scripts/virtual_devices.py) passent par le vrai moteur (enregistrement, analyse, chien de garde),
sur DURATION secondes qui se terminent maintenant. Quelques anomalies sont injectées vers la fin
pour que la démonstration montre des alertes récentes.

La base et les modèles de démonstration sont écrits dans data/demo/ : la base et les modèles
du prototype ne sont pas touchés. Utile aussi comme plan B de soutenance (pas de réseau requis).

Usage :
  python scripts/demo_seed.py
  # Windows : $env:DB_PATH="data/demo/mysa-demo.db"; uvicorn api.main:app
  # Linux   : DB_PATH=data/demo/mysa-demo.db uvicorn api.main:app
"""
import argparse
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DURATION = 2400
EVENTS = [
    {"t": 1500, "device": "virt-door-01", "sensor": "magnet", "type": "flood", "duration": 40, "factor": 20},
    {"t": 2050, "device": "virt-climate-01", "sensor": "temperature", "type": "spike", "value": 41.0},
    {"t": 2200, "device": "virt-hall-01", "sensor": "pir", "type": "flapping", "duration": 60},
    {"t": 2250, "device": "virt-bulb-01", "sensor": "bulb_state", "type": "silence", "duration": 200},
]


def main():
    ap = argparse.ArgumentParser(description="Base de démonstration du dashboard")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "demo"))
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    os.makedirs(os.path.join(args.out, "models"))
    os.environ["DB_PATH"] = os.path.join(args.out, "mysa-demo.db")
    os.environ["MYSA_MODELS_DIR"] = os.path.join(args.out, "models")

    from engine import analyzer, storage, watchdog
    from virtual_devices import run

    storage.init_db()
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=DURATION)
    clock = {"next": 5.0}

    def emit(topic, p):
        vt = (datetime.fromisoformat(p["ts"]) - start).total_seconds()
        while vt >= clock["next"]:
            watchdog.check_silence(now=start + timedelta(seconds=clock["next"]))
            clock["next"] += 5.0
        ts = storage.record_message(p["device_id"], p["sensor"], p["value"], p["unit"], p["ts"])
        analyzer.evaluate(p["device_id"], p["sensor"], ts, p["unit"])

    sent = run(emit, EVENTS, DURATION, 1, seed=args.seed, realtime=False, start_wall=start)
    watchdog.check_silence(now=now)
    n_alerts = len(storage.list_alerts(100000))
    print(f"{sent} messages, {n_alerts} alertes, {len(storage.list_episodes(1000))} épisodes -> {os.environ['DB_PATH']}")
    print("Lancer l'API sur cette base : DB_PATH=" + os.path.relpath(os.environ["DB_PATH"], ROOT)
          + " puis uvicorn api.main:app")


if __name__ == "__main__":
    main()
