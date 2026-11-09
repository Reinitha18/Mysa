"""
Exécute les scénarios d'intrusion TI-01 à TI-05 contre le hub Mysa et produit un rapport
« avant / après » (Markdown) : pour chaque attaque, ce qu'elle donnerait SANS les protections de
Mysa (analyse du chapitre 4) et ce qu'elle donne AVEC (mesuré maintenant : bloqué, détecté, délai).

À lancer depuis la VM Kali, le hub étant en marche :
  python3 attack-lab/run_report.py --out attack-lab/report.md
La campagne est aussi enregistrée dans le journal de validation du dashboard (page « Validation »),
sauf avec --no-push.

⚠️ Lab uniquement, sur le prototype Mysa, réseau isolé. Voir attack-lab/README.md.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, os.path.join(HERE, "scenarios"))

from common import api_get, api_post, load_cfg  # noqa: E402
import ti01_ecoute, ti02_bruteforce, ti03_usurpation, ti04_saturation, ti05_camera  # noqa: E402

SCENARIOS = [ti01_ecoute, ti02_bruteforce, ti03_usurpation, ti04_saturation, ti05_camera]

# Ce que donnerait l'attaque sur le système AVANT durcissement (analyse des vulnérabilités, ch. 4).
AVANT = {
    "TI-01": "Réussie : trafic en clair, lecture possible (V-01) ; connexion anonyme (V-02).",
    "TI-02": "Réussie : identifiants par défaut / faibles (V-02).",
    "TI-03": "Réussie : ni ACL ni validation — usurpation, commandes et télémétrie forgées acceptées.",
    "TI-04": "Non détectée : aucune surveillance du rythme des messages.",
    "TI-05": "Réussie : flux caméra accessible, pas de cloisonnement.",
}


def wait_detection(cfg, ev, timeout=25.0):
    """Cherche une alerte Mysa correspondant à l'attaque (device + capteur + mot-clé) depuis ev.since.
    Retourne (détecté ?, délai en s ou None)."""
    if not ev:
        return False, None
    since = ev["since"]
    keyword = ev.get("attendu", "").lower()
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            alerts = api_get(cfg, "/api/alerts?limit=300")
        except Exception:
            time.sleep(1.0)
            continue
        for a in alerts:
            if a.get("device_id") == ev["device_id"] and a.get("sensor") == ev["sensor"] \
                    and (a.get("ts") or "") >= since:
                blob = f"{a.get('source', '')} {a.get('message', '')}".lower()
                if not keyword or keyword in blob:
                    delay = (datetime.fromisoformat(a["ts"].replace("Z", "+00:00"))
                             - datetime.fromisoformat(since.replace("Z", "+00:00"))).total_seconds()
                    return True, max(delay, 0.0)
        time.sleep(1.5)
    return False, None


def verdict(res, detected, delay):
    if res.get("bloque"):
        return "🛡️ Bloqué"
    if detected:
        return f"🔎 Détecté (~{delay:.0f} s)"
    if res.get("execute"):
        return "⚠️ Exécuté, non détecté"
    return "— non exécuté"


def status_of(res, detected):
    """Verdict sous forme de code, pour le journal de validation du hub (mêmes règles que verdict())."""
    if res.get("bloque"):
        return "blocked"
    if detected:
        return "detected"
    return "undetected" if res.get("execute") else "not_run"


def push_run(cfg, started, finished, rows):
    """Envoie la campagne au journal de validation du dashboard (POST /api/validation/runs)."""
    payload = {
        "started_ts": started, "finished_ts": finished, "target": cfg["host"],
        "results": [{"ti": res["ti"], "name": res["nom"], "before": AVANT.get(res["ti"]), "status": status,
                     "delay_s": delay, "note": res["note"]} for res, status, delay in rows],
    }
    return api_post(cfg, "/api/validation/runs", payload)["id"]


def main():
    ap = argparse.ArgumentParser(description="Rapport avant/après du lab d'attaque Mysa")
    ap.add_argument("--out", default=os.path.join(HERE, "report.md"))
    ap.add_argument("--detect-timeout", type=float, default=25.0)
    ap.add_argument("--no-push", action="store_true",
                    help="ne pas envoyer la campagne au journal de validation du dashboard")
    args = ap.parse_args()
    cfg = load_cfg()

    print(f"Cible : {cfg['host']} (MQTT {cfg['mqtt_port']}, API {cfg['api_base']})\n")
    rows, journal = [], []
    started = datetime.now(timezone.utc).isoformat()
    for mod in SCENARIOS:
        res = mod.run(cfg)
        detected, delay = wait_detection(cfg, res.get("evidence"), args.detect_timeout)
        v = verdict(res, detected, delay)
        # Vérification ACL côté défenseur (TI-03) : l'usurpation d'un autre nœud a-t-elle été jetée ?
        ev = res.get("evidence") or {}
        if ev.get("acl"):
            try:
                hist = api_get(cfg, "/api/devices/esp32-cmf-01/history?sensor=pir&limit=1")
                blocked_acl = not any((h.get("ts") or "") >= ev["since"] for h in hist)
            except Exception:
                blocked_acl = True  # 404 = aucune télémétrie : l'usurpation n'est pas passée
            res["note"] += (" | ACL : usurpation de esp32-cmf-01 "
                            + ("BLOQUÉE (aucune télémétrie reçue)" if blocked_acl else "PASSÉE — à corriger !"))
        print(f"{res['ti']}  {res['nom']:<28} -> {v}")
        print(f"        {res['note']}")
        rows.append((res, v))
        journal.append((res, status_of(res, detected), delay))

    finished = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Lab d'attaque Mysa — rapport avant / après",
        "",
        f"_Généré le {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — cible {cfg['host']}._",
        "",
        "« Avant » : résultat attendu sur le système non durci (analyse des vulnérabilités, chapitre 4). ",
        "« Après » : résultat **mesuré** sur Mysa (bloqué par TLS/auth/ACL/pare-feu, ou détecté par le moteur).",
        "",
        "| TI | Attaque | Avant (sans Mysa) | Après (Mysa) | Observations |",
        "|----|---------|-------------------|--------------|--------------|",
    ]
    for res, v in rows:
        note = res["note"].replace("|", "\\|")
        lines.append(f"| {res['ti']} | {res['nom']} | {AVANT.get(res['ti'], '—')} | {v} | {note} |")
    lines += [
        "",
        "## Lecture",
        "- **Bloqué** : l'attaque n'a pas pu s'exécuter (chiffrement, authentification, ACL du broker "
        "ou segmentation réseau l'en ont empêchée).",
        "- **Détecté** : l'attaque s'est exécutée mais le moteur a levé une alerte (délai = temps "
        "jusqu'à la première alerte).",
        "- **Exécuté, non détecté** : à analyser — p. ex. la saturation (TI-04) n'est détectée "
        "qu'une fois le modèle du flux appris (voir scripts/replay_eval.py, sc02), et le canal caméra "
        "(TI-05) est protégé par la segmentation réseau plutôt que par une détection applicative.",
    ]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nRapport écrit : {args.out}")
    if not args.no_push:
        try:
            print(f"Campagne n° {push_run(cfg, started, finished, journal)} enregistrée dans le journal de validation du dashboard.")
        except Exception as err:  # le rapport Markdown reste produit : l'envoi est un plus
            print(f"⚠️  Journal de validation non mis à jour ({err}). Accès : DASHBOARD_EMAIL / DASHBOARD_PASSWORD dans lab.env.")


if __name__ == "__main__":
    main()
