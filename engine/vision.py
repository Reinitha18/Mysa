"""
Détection de mouvement par comparaison d'images (mémoire, chapitre 8, caméra du téléphone).

Le hub ne décode pas le flux vidéo : la page caméra du téléphone (camera/index.html) envoie, pour
chaque image, une VIGNETTE en niveaux de gris très réduite (par ex. 32×24). Le hub compare la
vignette courante à la précédente : on compte la part de pixels qui ont sensiblement changé ; si
elle dépasse un seuil, il y a mouvement. Comparaison faite sur le hub, en numpy seul (aucune
dépendance de traitement d'image, pas d'enregistrement d'images).

Le détecteur a une hystérésis simple pour éviter de publier sans arrêt :
  - front montant (repos -> mouvement)        : renvoie "start" (publier motion=1) ;
  - fin de mouvement, après COOLDOWN_S de calme : renvoie "stop"  (publier motion=0) ;
  - sinon                                       : renvoie None.

Les premières images (réglage d'exposition de la caméra) sont ignorées (WARMUP).
"""

import numpy as np

PIXEL_THRESHOLD = 25    # écart de luminance (0-255) à partir duquel un pixel est « changé »
AREA_THRESHOLD = 0.04   # part de pixels changés à partir de laquelle on parle de mouvement (4 %)
COOLDOWN_S = 8.0        # calme requis avant de déclarer la fin du mouvement
WARMUP = 2              # images ignorées au démarrage (stabilisation de la caméra)


class MotionDetector:
    def __init__(self, pixel_threshold=PIXEL_THRESHOLD, area_threshold=AREA_THRESHOLD,
                 cooldown_s=COOLDOWN_S, warmup=WARMUP):
        self.pixel_threshold = pixel_threshold
        self.area_threshold = area_threshold
        self.cooldown_s = cooldown_s
        self.warmup = warmup
        self.prev = None
        self.active = False
        self.last_motion_ts = None
        self.seen = 0
        self.last_fraction = 0.0

    def update(self, gray, ts_s: float) -> str | None:
        """gray : vignette en niveaux de gris (2D ou 1D), ts_s : horodatage en secondes.
        Retourne "start", "stop" ou None."""
        g = np.asarray(gray, dtype=np.int16).ravel()
        prev, self.prev = self.prev, g
        self.seen += 1
        if prev is None or prev.shape != g.shape or self.seen <= self.warmup:
            return None
        self.last_fraction = float(np.mean(np.abs(g - prev) > self.pixel_threshold))

        if self.last_fraction >= self.area_threshold:
            self.last_motion_ts = ts_s
            if not self.active:
                self.active = True
                return "start"
            return None
        if self.active and self.last_motion_ts is not None and ts_s - self.last_motion_ts >= self.cooldown_s:
            self.active = False
            return "stop"
        return None
