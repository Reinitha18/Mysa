"""Notifications (engine/notify.py) : quoi notifier, choix des canaux configurés, et branchement
sur insert_alert. Aucun envoi réseau réel : les transports sont remplacés par des sondes."""
from engine import notify
from engine.storage import insert_alert, set_alert_hook


def test_should_notify():
    assert notify.should_notify("high", "anomaly", True)       # alerte forte, nouvel épisode
    assert notify.should_notify("medium", "offline", True)     # nœud hors ligne
    assert not notify.should_notify("high", "anomaly", False)  # alerte déjà notifiée (même épisode)
    assert not notify.should_notify("medium", "anomaly", True) # gravité moyenne : pas de notification
    assert not notify.should_notify("low", "rule", True)


def test_dispatch_n_utilise_que_les_canaux_configures(monkeypatch):
    sent = []
    # Un seul canal « branché » : l'e-mail renvoie True, les autres False (non configurés).
    monkeypatch.setattr(notify, "send_email", lambda s, b: sent.append(("email", s, b)) or True)
    monkeypatch.setattr(notify, "send_sms", lambda t: False)
    monkeypatch.setattr(notify, "CHANNELS", {
        "e-mail": lambda s, b: notify.send_email(s, b),
        "SMS": lambda s, b: notify.send_sms(f"{s}\n{b}"),
    })
    done = notify.dispatch("esp32-sec-01", "Alarme déclenchée", "high", "rule")
    assert done == ["e-mail"] and sent[0][0] == "email" and "ALERTE" in sent[0][1]


def test_un_canal_en_echec_n_empeche_pas_les_autres(monkeypatch):
    def boom(*_a):
        raise RuntimeError("SMTP indisponible")
    monkeypatch.setattr(notify, "send_email", boom)
    monkeypatch.setattr(notify, "send_sms", lambda t: True)
    monkeypatch.setattr(notify, "CHANNELS", {
        "e-mail": lambda s, b: notify.send_email(s, b),
        "SMS": lambda s, b: notify.send_sms(f"{s}\n{b}"),
    })
    assert notify.dispatch("n", "msg", "high", "offline") == ["SMS"]


def test_hook_sur_insert_alert(monkeypatch):
    recu = []
    monkeypatch.setattr(notify, "on_alert", recu.append)
    set_alert_hook(notify.on_alert)
    try:
        insert_alert("esp32-sec-01", "Alarme", severity="high", ts="2026-01-01T00:00:00+00:00",
                     sensor="alarm", kind="rule")
        insert_alert("esp32-sec-01", "badge refusé", severity="low", ts="2026-01-01T00:00:01+00:00",
                     sensor="rfid", kind="rule")
    finally:
        set_alert_hook(None)
    assert len(recu) == 2
    assert recu[0]["severity"] == "high" and recu[0]["new_episode"] is True
    assert recu[0]["device_id"] == "esp32-sec-01" and recu[0]["kind"] == "rule"
