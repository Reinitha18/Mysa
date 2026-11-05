"""Corrélation entre capteurs (engine/correlation.py) : les trois scénarios du chapitre 8,
et l'absence de fausse alerte quand le contexte ne s'y prête pas."""
from datetime import datetime, timedelta, timezone

from engine import correlation, ingest
from engine.storage import list_alerts

# Midi UTC = 15 h locale (UTC+3 par défaut) : hors des heures creuses, pour ne pas déclencher C-03
# par accident dans les tests de présence.
NOON = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def at(base: datetime, s: float = 0) -> str:
    return (base + timedelta(seconds=s)).isoformat()


def send(device, sensor, value, unit, ts, **meta):
    ingest.handle_telemetry({"device_id": device, "sensor": sensor, "value": value, "unit": unit,
                             "ts": ts, "meta": meta})


def corr_sources():
    return [a["source"] for a in list_alerts() if (a["source"] or "").startswith("corrélation")]


def corr_alerts():
    return [a for a in list_alerts() if (a["source"] or "").startswith("corrélation")]


# ---------------------------------------------------------------- C-01
def test_c01_mouvement_sans_acces_alarme_armee():
    send("esp32-sec-01", "arm", 1, "bool", at(NOON))
    send("esp32-sec-01", "pir", 1, "bool", at(NOON, 200))  # après le délai de sortie
    a = corr_alerts()
    assert len(a) == 1 and a[0]["severity"] == "high"
    assert a[0]["source"] == "corrélation : mouvement sans accès"


def test_c01_supprime_si_badge_valide_recent():
    send("esp32-sec-01", "arm", 1, "bool", at(NOON))
    send("esp32-sec-01", "rfid", 1, "bool", at(NOON, 190))  # badge accepté juste avant
    send("esp32-sec-01", "pir", 1, "bool", at(NOON, 200))
    assert "corrélation : mouvement sans accès" not in corr_sources()


def test_c01_supprime_pendant_le_delai_de_sortie():
    send("esp32-sec-01", "arm", 1, "bool", at(NOON))
    send("esp32-sec-01", "pir", 1, "bool", at(NOON, 30))   # dans le délai de sortie
    assert corr_sources() == []


def test_c01_rien_si_alarme_desarmee():
    send("esp32-sec-01", "arm", 0, "bool", at(NOON))
    send("esp32-sec-01", "pir", 1, "bool", at(NOON, 200))
    assert corr_sources() == []


# ---------------------------------------------------------------- C-02
def test_c02_presence_confirmee_pir_et_camera():
    send("esp32-sec-01", "arm", 1, "bool", at(NOON))
    send("esp32-sec-01", "pir", 1, "bool", at(NOON, 200))
    send("cam-01", "motion", 1, "bool", at(NOON, 210), armed=True)
    assert "corrélation : présence confirmée" in corr_sources()


# ---------------------------------------------------------------- C-03
def test_c03_badge_heure_creuse(monkeypatch):
    monkeypatch.setattr(correlation, "LOCAL_UTC_OFFSET_H", 0.0)  # UTC = heure locale, test déterministe
    nuit = datetime(2026, 1, 1, 3, tzinfo=timezone.utc)          # 3 h : heure creuse par défaut
    send("esp32-sec-01", "rfid", 1, "bool", at(nuit))
    a = corr_alerts()
    assert len(a) == 1 and a[0]["severity"] == "medium"
    assert "03 h" in a[0]["message"]


def test_c03_heure_inhabituelle_apprise(monkeypatch):
    monkeypatch.setattr(correlation, "LOCAL_UTC_OFFSET_H", 0.0)
    jour = datetime(2026, 1, 1, 14, tzinfo=timezone.utc)   # 14 h : heure habituelle
    for i in range(30):                                     # on apprend l'habitude (>= MIN_ACCESS_HISTORY)
        send("esp32-sec-01", "rfid", 1, "bool", at(jour, i * 86400))  # un accès par jour à 14 h
    avant = len(corr_alerts())
    send("esp32-sec-01", "rfid", 1, "bool", at(jour, 30 * 86400 + 3600 * 3))  # 17 h, jamais vue
    nouveaux = corr_alerts()[avant:]
    assert any("heure inhabituelle" in a["source"] and "17 h" in a["message"] for a in nouveaux)


def test_c03_heure_habituelle_sans_alerte(monkeypatch):
    monkeypatch.setattr(correlation, "LOCAL_UTC_OFFSET_H", 0.0)
    jour = datetime(2026, 1, 1, 14, tzinfo=timezone.utc)
    for i in range(30):
        send("esp32-sec-01", "rfid", 1, "bool", at(jour, i * 86400))
    assert corr_sources() == []  # 14 h est l'heure habituelle : aucune alerte de corrélation
