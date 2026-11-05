"""Détection de mouvement par comparaison d'images (engine/vision.py)."""
from engine.vision import MotionDetector

CALME = [10] * 768          # vignette 32×24 uniforme
BOUGE = [240] * 768         # très différente -> mouvement


def test_images_identiques_pas_de_mouvement():
    d = MotionDetector()
    assert d.update(CALME, 0) is None   # 1re image : pas de référence
    assert d.update(CALME, 1) is None   # warmup
    assert d.update(CALME, 2) is None   # identique -> rien
    assert d.update(CALME, 3) is None


def test_front_montant_puis_fin_apres_cooldown():
    # Le détecteur réagit au CHANGEMENT entre images consécutives. Le dernier changement est le
    # retour de BOUGE à CALME (ts=3) ; ensuite, des images calmes identiques laissent courir le cooldown.
    d = MotionDetector(cooldown_s=8.0)
    d.update(CALME, 0)
    d.update(CALME, 1)                  # warmup terminé, référence = CALME
    assert d.update(BOUGE, 2) == "start"      # changement franc -> début de mouvement
    assert d.update(CALME, 3) is None         # encore un changement : mouvement toujours actif
    assert d.update(CALME, 4) is None         # calme (identique), cooldown pas écoulé
    assert d.update(CALME, 12) == "stop"      # 8 s de calme après le dernier mouvement -> fin


def test_fraction_changee_sous_le_seuil_ignoree():
    d = MotionDetector(area_threshold=0.5)  # il faut 50 % de pixels changés
    d.update([0] * 768, 0)
    d.update([0] * 768, 1)
    petit = [0] * 768
    for i in range(10):  # ~1,3 % des pixels changent : sous le seuil
        petit[i] = 255
    assert d.update(petit, 2) is None


def test_taille_incoherente_sans_plantage():
    d = MotionDetector()
    d.update([0] * 768, 0)
    d.update([0] * 768, 1)
    assert d.update([0] * 300, 2) is None  # vignette de taille différente : ignorée proprement
