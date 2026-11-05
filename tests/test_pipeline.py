"""Bout en bout : scénarios des appareils virtuels rejoués dans le moteur (scripts/replay_eval.py)."""
import replay_eval


def test_fonctionnement_normal_sans_fausse_alerte():
    r = replay_eval.replay("sc00", 1)
    assert r["episodes_faux"] == 0


def test_pics_detectes_par_l_enveloppe():
    r = replay_eval.replay("sc01", 1)
    assert all(e["detectee"] for e in r["evenements"])
    assert all(e["delai_s"] < 10 for e in r["evenements"])


def test_inondation_detectee_par_le_rythme():
    (e,) = replay_eval.replay("sc02", 1)["evenements"]
    assert e["detectee"] and e["delai_s"] < 10 and "rythme" in e["source"]


def test_derive_detectee_par_la_tendance():
    (e,) = replay_eval.replay("sc03", 1)["evenements"]
    assert e["detectee"] and "tendance" in e["source"]


def test_historique_d_apprentissage_survit_au_redemarrage():
    from engine import analyzer
    from engine.storage import record_message
    for i in range(80):
        ts = f"2026-01-01T00:{i * 2 // 60:02d}:{i * 2 % 60:02d}+00:00"
        record_message("d", "t", 20.0 + (i % 3) * 0.1, "C", ts)
        analyzer.evaluate("d", "t", ts, "C")
    n = len(analyzer._state["d__t"]["history"])
    assert n > 0
    analyzer.reset()  # simule un redémarrage du moteur
    ts = "2026-01-01T00:02:40+00:00"
    record_message("d", "t", 20.0, "C", ts)
    analyzer.evaluate("d", "t", ts, "C")
    assert len(analyzer._state["d__t"]["history"]) >= n


def test_oscillation_d_un_capteur_binaire_apres_apprentissage():
    r = replay_eval.replay("sc06", 1)
    assert all(e["detectee"] and "bascules" in e["source"] for e in r["evenements"])
    assert r["episodes_faux"] == 0
