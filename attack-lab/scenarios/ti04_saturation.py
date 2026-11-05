"""TI-04 — Saturation (inondation de messages, déni de service applicatif).

Risque visé : R-04 (disponibilité). Avec un nœud compromis (STOLEN_USER), l'attaquant publie très
vite un grand nombre de messages sur son propre flux (home/esp32-sec-01/pir).

Attendu sur Mysa : le broker et le moteur restent debout ; le détecteur de RYTHME du moteur (SC-02)
lève une alerte quand le flux a déjà un modèle appris. Sur un flux « froid » (sans modèle), la
saturation est encodée mais pas encore détectée — c'est pourquoi la mesure « avant/après » se fait
après une période d'apprentissage (voir scripts/replay_eval.py, scénario sc02).
"""
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from common import load_cfg, mqtt_client, try_connect  # noqa: E402

BURST = int(os.getenv("FLOOD_COUNT", "500"))


def run(cfg: dict) -> dict:
    u, p = cfg["stolen_user"], cfg["stolen_password"]
    since = datetime.now(timezone.utc).isoformat()
    ok, detail = try_connect(cfg, u, p, use_tls=True)
    if not ok:
        return {"ti": "TI-04", "nom": "Saturation", "execute": False, "bloque": True,
                "note": f"connexion refusée : {detail}", "evidence": None}
    c = mqtt_client("ti-flood", cfg, u, p, use_tls=True)
    c.connect(cfg["host"], cfg["mqtt_port"], keepalive=10)
    c.loop_start()
    t0 = time.time()
    sent = 0
    for i in range(BURST):
        c.publish("home/esp32-sec-01/pir", '{"value": %d, "unit": "bool"}' % (i % 2), qos=0)
        sent += 1
    time.sleep(0.5)
    c.loop_stop()
    c.disconnect()
    rate = sent / max(time.time() - t0, 0.001)
    note = f"{sent} messages envoyés en rafale (~{rate:.0f} msg/s) sur home/esp32-sec-01/pir"
    return {"ti": "TI-04", "nom": "Saturation", "execute": True, "bloque": False, "note": note,
            "evidence": {"since": since, "device_id": "esp32-sec-01", "sensor": "pir",
                         "attendu": "rythme"}}


if __name__ == "__main__":
    print(run(load_cfg()))
