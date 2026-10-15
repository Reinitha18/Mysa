"""
Catégories d'appareils et association capteur -> catégorie.

Un modèle de référence est entraîné par catégorie, sur le dataset public qui
lui correspond (jamais de mélange entre catégories). Quand un nouveau flux
capteur apparaît, on lui associe la catégorie la plus proche grâce au nom du
capteur (ex. "dht22" -> "environnemental"). Un capteur sans catégorie connue
(RFID, relais, servomoteur...) n'a pas de modèle de référence : son
apprentissage repart de zéro, comme dans la version initiale du moteur.
"""

# Mots-clés (en minuscules) reconnus dans le nom du capteur.
SENSOR_KEYWORDS = {
    "mouvement": ["pir", "hc-sr501", "motion", "mouvement"],
    "ouverture": ["magnet", "reed", "door", "contact", "ouverture"],
    "environnemental": ["dht22", "dht11", "temperature", "humidity", "weather", "temp"],
    "geolocalisation": ["gps", "latitude", "longitude", "geoloc"],
}

# Dataset public d'entraînement par catégorie (TON_IoT, télémétrie IoT).
# Les noms de colonnes sont à vérifier à l'ouverture des CSV téléchargés.
CATEGORY_DATASETS = {
    "mouvement": {"file": "IoT_Motion_Light.csv", "value_col": "motion_status"},
    "ouverture": {"file": "IoT_Garage_Door.csv", "value_col": "door_state"},
    "environnemental": {"file": "IoT_Weather.csv", "value_col": "temperature"},
    "geolocalisation": {"file": "IoT_GPS_Tracker.csv", "value_col": "latitude"},
}


def categorize(sensor: str) -> str | None:
    """Retourne la catégorie la plus proche du nom de capteur, ou None."""
    name = (sensor or "").strip().lower()
    for category, keywords in SENSOR_KEYWORDS.items():
        if name in keywords:
            return category
    for category, keywords in SENSOR_KEYWORDS.items():
        if any(k in name for k in keywords):
            return category
    return None
