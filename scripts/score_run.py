"""
Compare la vérité terrain d'un scénario d'appareils virtuels (data/runs/last_events.json) aux
alertes enregistrées par le moteur (base SQLite), et résume : anomalies détectées, délai,
source de la détection, et fausses alertes hors des fenêtres d'anomalie.

Une anomalie est « détectée » si une alerte du même flux (appareil + capteur) tombe entre son
début et sa fin, prolongée de TAIL_S secondes (le temps d'une fenêtre d'analyse). Les alertes
de type « notice » (avis de rejet d'une référence) ne comptent pas comme détection ni comme fausse alerte.

Attention : toutes les alertes de la base sont comptées. Repartir d'une base vide avant chaque
scénario (supprimer mysa.db), sinon les fausses alertes des runs précédents s'additionnent.
Pour une évaluation reproductible sans broker, voir scripts/replay_eval.py.

Usage : python scripts/score_run.py [--events data/runs/last_events.json] [--out data/runs/score.json]
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TAIL_S = 60.0


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def score(truth: dict, alerts: list[dict], verbose: bool = False) -> dict:
    """Note un run : `truth` au format de last_events.json, `alerts` = alertes anomaly/silence."""
    alerts = sorted(alerts, key=lambda a: a["ts"])
    windows = [(e, parse(e["start_ts"]), parse(e["end_ts"])) for e in truth["events"]]

    def in_window(a, e, start, end):
        if (a["device_id"], a["sensor"]) != (e["device"], e["sensor"]):
            return False
        t = parse(a["ts"])
        return 0 <= (t - start).total_seconds() and (t - end).total_seconds() <= TAIL_S

    results = []
    for e, start, end in windows:
        hits = [a for a in alerts if in_window(a, e, start, end)]
        first = hits[0] if hits else None
        res = {"flux": f"{e['device']}/{e['sensor']}", "type": e["type"], "t": e["t"], "detectee": bool(hits),
               "delai_s": round((parse(first["ts"]) - start).total_seconds(), 1) if first else None,
               "source": first["source"] if first else None, "alertes": len(hits)}
        results.append(res)
        if verbose:
            print(f"  {res['flux']:<28} {e['type']:<9} t={e['t']:<6} -> "
                  + (f"DÉTECTÉE après {res['delai_s']} s par « {res['source']} » ({res['alertes']} alertes)"
                     if res["detectee"] else "NON DÉTECTÉE"))

    false_alerts = [a for a in alerts if not any(in_window(a, e, s, en) for e, s, en in windows)]
    # Un épisode qui contient une détection n'est pas un épisode faux, même si ses dernières alertes
    # (retour à la normale après l'attaque) tombent après la marge TAIL_S.
    true_episodes = {a["episode_id"] for a in alerts if a not in false_alerts}
    by_flow = {}
    for a in false_alerts:
        if a["episode_id"] not in true_episodes:
            by_flow.setdefault(f"{a['device_id']}/{a['sensor']}", set()).add(a["episode_id"])
    return {"scenario": truth.get("preset"), "seed": truth.get("seed"), "evenements": results,
            "fausses_alertes": len(false_alerts),
            "episodes_faux": sum(len(eps) for eps in by_flow.values()),
            "episodes_faux_par_flux": {f: len(eps) for f, eps in sorted(by_flow.items())}}


def main():
    from engine.storage import list_alerts

    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="data/runs/last_events.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    truth = json.load(open(args.events, encoding="utf-8"))
    alerts = [a for a in list_alerts(100000) if a["kind"] in ("anomaly", "silence")]
    print(f"Scénario : {truth.get('preset')}  (graine {truth.get('seed')}, vitesse x{truth.get('speed')})\n")
    res = score(truth, alerts, verbose=True)
    print(f"\nFausses alertes (hors fenêtres d'anomalie) : {res['fausses_alertes']} alertes "
          f"en {res['episodes_faux']} épisodes")
    for flow, n in res["episodes_faux_par_flux"].items():
        print(f"   {flow:<28} {n} épisode(s)")
    if args.out:
        json.dump(res, open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
