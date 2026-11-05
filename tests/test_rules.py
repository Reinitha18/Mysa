from datetime import datetime, timedelta, timezone

from engine import analyzer, ingest, risk, rules, watchdog
from engine.storage import list_access, list_alerts, list_presence, list_streams, record_message

NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def at(s: float) -> str:
    return (NOW + timedelta(seconds=s)).isoformat()


def send(device, sensor, value, unit, t, **meta):
    ingest.handle_telemetry({"device_id": device, "sensor": sensor, "value": value, "unit": unit,
                             "ts": at(t), "meta": meta})


def sources():
    return [a["source"] for a in list_alerts()]


def test_valeurs_hors_contrat():
    assert rules.evaluate("n", "pir", 999, "bool", at(0))[0]["severity"] == "high"
    assert rules.evaluate("n", "humidity", 140, "%", at(0))[0]["rule"] == "valeur hors contrat"
    assert rules.evaluate("n", "pir", 1, "bool", at(0)) == []


def test_temperature_surchauffe_et_variation_brutale():
    send("c", "temperature", 23.0, "C", 0)
    send("c", "temperature", 23.1, "C", 5)
    assert list_alerts() == []
    send("c", "temperature", 47.0, "C", 10)
    assert {"règle : surchauffe", "règle : variation brutale"} <= set(sources())


def test_badges_refuses_puis_rafale():
    send("s", "rfid", 0, "bool", 0, uid="AA BB CC DD")
    assert list_alerts() == []  # un refus isolé est consigné au journal des accès, sans alerte
    assert list_access()[0]["uid"] == "AA BB CC DD" and list_access()[0]["granted"] == 0
    send("s", "rfid", 0, "bool", 10)
    send("s", "rfid", 0, "bool", 20)
    alerts = list_alerts()
    assert [a["source"] for a in alerts] == ["règle : accès refusés répétés"]
    assert alerts[0]["severity"] == "medium"  # pas critique : pas de notification
    send("s", "rfid", 1, "bool", 30)  # badge valide : aucune alerte supplémentaire
    assert len(list_alerts()) == 1 and len(list_access()) == 4


def test_lecteur_bloque_avec_duree():
    send("s", "rfid_lockout", 30, "s", 0)
    a = list_alerts()[0]
    assert a["severity"] == "high" and "pendant 30 s" in a["message"]
    send("s", "rfid_lockout", 0, "s", 30)  # fin du blocage : pas d'alerte
    assert len(list_alerts()) == 1


def test_alarme_avec_cause():
    send("s", "alarm", 1, "bool", 0, cause="porte ouverte sans badge")
    a = list_alerts()[0]
    assert a["severity"] == "high" and "porte ouverte sans badge" in a["message"]


def test_presence_last_will():
    m = ingest.parse_message("home/esp32-sec-01/status", b"offline", at(0))
    assert m == {"device_id": "esp32-sec-01", "presence": "offline", "ts": at(0)}
    ingest.handle_presence("esp32-sec-01", True, at(0))
    ingest.handle_presence("esp32-sec-01", False, at(10))
    ingest.handle_presence("esp32-sec-01", False, at(11))  # republication : pas de doublon
    assert [a["kind"] for a in list_alerts()] == ["offline"]
    assert list_presence()["esp32-sec-01"]["online"] is False
    r = risk.device_risks(now=NOW + timedelta(seconds=11))["esp32-sec-01"]
    assert r["offline"] and r["score"] >= risk.OFFLINE_WEIGHT


def test_chien_de_garde_ignore_les_flux_evenementiels():
    for i in range(12):  # rythme établi sur un flux événementiel ET un flux périodique
        record_message("s", "rfid", 1, "bool", at(i))
        record_message("s", "pir", 0, "bool", at(i))
    watchdog.check_silence(now=NOW + timedelta(hours=1))
    silent = {s["sensor"] for s in list_streams() if s["silent"]}
    assert silent == {"pir"}


def test_flux_evenementiel_non_analyse_par_le_modele():
    for i in range(60):
        send("s", "lock", i % 2, "bool", i)
    assert not any(s["regime"] for s in list_streams() if s["sensor"] == "lock")


def test_grace_du_rythme_apres_reconnexion():
    ingest.handle_presence("c", True, at(0))
    assert analyzer._in_grace("c", at(60)) and not analyzer._in_grace("c", at(300))
    assert not analyzer._in_grace("autre", at(60))
