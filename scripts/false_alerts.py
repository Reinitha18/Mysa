"""
Mesure des fausses alertes (mémoire, chapitre 9, objectif : moins d'une fausse alerte par jour).

Principe : on rejoue HORS LIGNE un fonctionnement NORMAL (aucune anomalie injectée) sur une durée
simulée longue, pour plusieurs graines, et sous deux configurations du moteur :

  avant : les modèles de référence lèvent des alertes (hypothèse H1 du mémoire) ;
  après : les références servent de simple filtre de la baseline (choix retenu pour Mysa).

Comme le scénario ne contient aucune anomalie, TOUT épisode d'alerte (anomaly ou silence) est une
fausse alerte. On rapporte le nombre d'épisodes de fausse alerte ramené à la journée :

    fausses alertes / jour = épisodes de fausse alerte / (durée simulée / 86400 s)

Le moteur, la base et les modèles ne sont jamais touchés : chaque run tourne dans une base et un
dossier de modèles temporaires (comme scripts/replay_eval.py).

Le résultat ne dépend PAS de la durée de chaque graine : la synthèse agrège le temps simulé de
toutes les graines d'une configuration (4 graines × 0,25 jour = 1 jour) pour le taux par jour.
Le rejeu est hors ligne mais reste coûteux (~1 min pour 0,05 jour simulé) : augmenter --days
donne une mesure plus fine, au prix du temps de calcul.

Usage :
  python scripts/false_alerts.py                                  # ~1 jour agrégé / config (4 × 0,25 j)
  python scripts/false_alerts.py --days 1 --seeds 1-3             # 1 jour par graine (plus long, plus fin)
  python scripts/false_alerts.py --configs apres --seeds 1-4      # une seule configuration
  python scripts/false_alerts.py --out data/runs/false_alerts.csv
"""
import argparse
import csv
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import replay_eval  # noqa: E402  (reset_engine, horloge virtuelle, chien de garde)
from virtual_devices import run  # noqa: E402

from engine import analyzer, storage, watchdog  # noqa: E402

DAY_S = 86400.0
SPEED = 5  # sans effet sur le résultat (rejeu hors ligne), accélère seulement l'horloge virtuelle

# Clés sans accent pour la ligne de commande ; libellé complet pour le mémoire.
CONFIGS = {
    "avant": {"label": "références actives (hypothèse H1)", "ref_alerts": True},
    "apres": {"label": "références en filtre seul (Mysa)", "ref_alerts": False},
}


def run_normal(duration_s: float, seed: int, ref_alerts: bool) -> dict:
    """Rejoue un fonctionnement normal et compte les épisodes de fausse alerte."""
    with tempfile.TemporaryDirectory(prefix="mysa-fa-") as tmp:
        replay_eval.reset_engine(tmp)
        analyzer.REF_ALERTS = ref_alerts  # bascule la configuration pour ce run
        clock = {"next_wd": replay_eval.WATCHDOG_EVERY_S}

        def emit(_topic, p):
            vt = (datetime.fromisoformat(p["ts"]) - replay_eval.START).total_seconds()
            while vt >= clock["next_wd"]:
                watchdog.check_silence(now=replay_eval.START + timedelta(seconds=clock["next_wd"]))
                clock["next_wd"] += replay_eval.WATCHDOG_EVERY_S
            ts = storage.record_message(p["device_id"], p["sensor"], p["value"], p["unit"], p["ts"])
            analyzer.evaluate(p["device_id"], p["sensor"], ts, p["unit"])

        sent = run(emit, [], duration_s, SPEED, seed=seed, realtime=False, start_wall=replay_eval.START)
        episodes = [e for e in storage.list_episodes(10 ** 6) if e["kind"] in ("anomaly", "silence")]
        by_flux: dict[str, int] = {}
        for e in episodes:
            by_flux[f"{e['device_id']}/{e['sensor']}"] = by_flux.get(f"{e['device_id']}/{e['sensor']}", 0) + 1
        return {"messages": sent, "episodes": len(episodes),
                "alertes": sum(e["alert_count"] for e in episodes), "par_flux": by_flux}


def parse_seeds(text: str) -> list[int]:
    if "-" in text:
        a, b = text.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in text.split(",")]


def main():
    ap = argparse.ArgumentParser(description="Mesure des fausses alertes en fonctionnement normal")
    ap.add_argument("--days", type=float, default=0.25, help="durée simulée par graine, en jours (défaut 0,25)")
    ap.add_argument("--seeds", default="1-4", help="graines, ex. 1-4 ou 1,3,7")
    ap.add_argument("--configs", default="avant,apres", help="configurations à comparer (avant,apres)")
    ap.add_argument("--out", default="data/runs/false_alerts.csv", help="fichier CSV de résultats")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR,
                        format="%(levelname)s %(message)s")

    duration_s = args.days * DAY_S
    seeds = parse_seeds(args.seeds)
    configs = [c.strip() for c in args.configs.split(",") if c.strip() in CONFIGS]
    if not configs:
        raise SystemExit(f"Configurations inconnues. Choisir parmi : {', '.join(CONFIGS)}")

    rows = []
    print(f"Fonctionnement normal rejoué : {args.days:g} jour(s) simulé(s) × {len(seeds)} graine(s) "
          f"par configuration.\n")
    header = f"{'config':<22} {'graine':>6} {'messages':>9} {'épis. faux':>11} {'alertes':>8} {'faux/jour':>10}"
    print(header)
    print("-" * len(header))
    for cfg in configs:
        for seed in seeds:
            r = run_normal(duration_s, seed, CONFIGS[cfg]["ref_alerts"])
            per_day = r["episodes"] / args.days
            print(f"{CONFIGS[cfg]['label']:<22} {seed:>6} {r['messages']:>9} {r['episodes']:>11} "
                  f"{r['alertes']:>8} {per_day:>10.2f}")
            rows.append({"config": cfg, "configuration": CONFIGS[cfg]["label"], "graine": seed,
                         "jours_simules": args.days, "messages": r["messages"],
                         "episodes_faux": r["episodes"], "alertes_fausses": r["alertes"],
                         "fausses_alertes_par_jour": round(per_day, 3),
                         "par_flux": ";".join(f"{k}={v}" for k, v in sorted(r["par_flux"].items()))})

    print("\nSynthèse par configuration (objectif : < 1 fausse alerte / jour) :")
    print(f"{'configuration':<34} {'épis. faux':>11} {'jours':>7} {'faux/jour':>10}  objectif")
    summary = []
    for cfg in configs:
        sub = [r for r in rows if r["config"] == cfg]
        total_ep = sum(r["episodes_faux"] for r in sub)
        total_days = sum(r["jours_simules"] for r in sub)
        per_day = total_ep / total_days if total_days else 0.0
        ok = "ATTEINT" if per_day < 1.0 else "NON ATTEINT"
        print(f"{CONFIGS[cfg]['label']:<34} {total_ep:>11} {total_days:>7.2f} {per_day:>10.2f}  {ok}")
        summary.append({"config": cfg, "configuration": CONFIGS[cfg]["label"], "graine": "TOTAL",
                        "jours_simules": round(total_days, 2), "messages": sum(r["messages"] for r in sub),
                        "episodes_faux": total_ep, "alertes_fausses": sum(r["alertes_fausses"] for r in sub),
                        "fausses_alertes_par_jour": round(per_day, 3), "par_flux": ""})

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fields = ["config", "configuration", "graine", "jours_simules", "messages", "episodes_faux",
              "alertes_fausses", "fausses_alertes_par_jour", "par_flux"]
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows + summary)
    print(f"\nTableau de résultats écrit dans {args.out} ({len(rows)} runs + {len(summary)} totaux).")


if __name__ == "__main__":
    main()
