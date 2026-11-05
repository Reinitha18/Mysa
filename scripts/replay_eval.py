"""
Banc d'essai HORS LIGNE du moteur : rejoue les scénarios des appareils virtuels
(scripts/virtual_devices.py) directement dans le moteur, sans broker MQTT ni attente
en temps réel, avec une base SQLite et un dossier de modèles TEMPORAIRES (la base et
les modèles du prototype ne sont jamais touchés).

Chaque message suit exactement le chemin de engine/ingest.py (record_message puis
analyzer.evaluate) ; le chien de garde est appelé toutes les WATCHDOG_EVERY_S secondes
virtuelles. Le résultat est noté par la même règle que scripts/score_run.py.

Pourquoi : comparer deux versions du moteur sur les mêmes scénarios et les mêmes graines,
en quelques secondes, et mesurer la dispersion sur plusieurs graines (chapitre 9 du mémoire).

Usage :
  python scripts/replay_eval.py                          # sc00 à sc06, graine 1
  python scripts/replay_eval.py --seeds 1-5              # 5 graines par scénario
  python scripts/replay_eval.py --presets sc00,sc03 --seeds 1-3 --out data/runs/replay.json
  python scripts/replay_eval.py --no-reference           # configuration « apprentissage depuis zéro »
"""
import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from virtual_devices import PRESETS, ground_truth, run  # noqa: E402
from score_run import score  # noqa: E402

from engine import analyzer, model, reference, storage, watchdog  # noqa: E402

WATCHDOG_EVERY_S = 5.0
START = datetime(2026, 1, 1, tzinfo=timezone.utc)  # horloge virtuelle fixe : runs reproductibles


def reset_engine(tmp: str):
    """Isole le moteur dans un dossier temporaire et remet à zéro son état en mémoire."""
    storage.DB_PATH = os.path.join(tmp, "replay.db")
    model.MODELS_DIR = os.path.join(tmp, "models")
    os.makedirs(model.MODELS_DIR, exist_ok=True)
    for mod in (analyzer, model, reference):
        for name in ("_state", "_published", "_cache"):
            if isinstance(getattr(mod, name, None), dict):
                getattr(mod, name).clear()
    if hasattr(analyzer, "reset"):
        analyzer.reset()
    storage.init_db()


def replay(preset: str, seed: int) -> dict:
    cfg = PRESETS[preset]
    events = list(cfg["events"])
    with tempfile.TemporaryDirectory(prefix="mysa-replay-") as tmp:
        reset_engine(tmp)
        clock = {"next_wd": WATCHDOG_EVERY_S}

        def emit(topic, p):
            vt = (datetime.fromisoformat(p["ts"]) - START).total_seconds()
            while vt >= clock["next_wd"]:  # chien de garde, à l'horloge virtuelle
                watchdog.check_silence(now=START + timedelta(seconds=clock["next_wd"]))
                clock["next_wd"] += WATCHDOG_EVERY_S
            ts = storage.record_message(p["device_id"], p["sensor"], p["value"], p["unit"], p["ts"])
            analyzer.evaluate(p["device_id"], p["sensor"], ts, p["unit"])

        sent = run(emit, events, cfg["duration"], cfg["speed"], seed=seed, realtime=False, start_wall=START)
        truth = {"preset": preset, "seed": seed, "events": ground_truth(events, START)}
        alerts = [a for a in storage.list_alerts(10 ** 6) if a["kind"] in ("anomaly", "silence")]
        res = score(truth, alerts)
        res["messages"] = sent
        return res


def parse_seeds(text: str) -> list[int]:
    if "-" in text:
        a, b = text.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in text.split(",")]


def main():
    ap = argparse.ArgumentParser(description="Rejeu hors ligne des scénarios virtuels dans le moteur")
    ap.add_argument("--presets", default="sc00,sc01,sc02,sc03,sc04,sc05,sc06")
    ap.add_argument("--seeds", default="1")
    ap.add_argument("--no-reference", action="store_true", help="désactive les modèles de référence")
    ap.add_argument("--out", default=None, help="écrit le détail au format JSON")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR,
                        format="%(levelname)s %(message)s")
    if args.no_reference:
        os.environ["MYSA_DISABLE_REFERENCE"] = "1"

    seeds = parse_seeds(args.seeds)
    rows = []
    print(f"{'scénario':<8} {'graine':>6} {'détectées':>10} {'délai moyen':>12} {'fausses alertes':>16} {'épisodes faux':>14}")
    for preset in args.presets.split(","):
        for seed in seeds:
            r = replay(preset, seed)
            det = [e for e in r["evenements"] if e["detectee"]]
            delay = (sum(e["delai_s"] for e in det) / len(det)) if det else None
            print(f"{preset:<8} {seed:>6} {len(det):>4}/{len(r['evenements']):<5} "
                  f"{(f'{delay:.1f} s' if delay is not None else '—'):>12} "
                  f"{r['fausses_alertes']:>16} {r['episodes_faux']:>14}")
            rows.append(r)
    n_ev = sum(len(r["evenements"]) for r in rows)
    n_det = sum(e["detectee"] for r in rows for e in r["evenements"])
    fa_ep = sum(r["episodes_faux"] for r in rows)
    print(f"\nTOTAL : {n_det}/{n_ev} anomalies détectées, {fa_ep} épisodes de fausse alerte "
          f"sur {len(rows)} runs ({fa_ep / len(rows):.1f} par run)")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
