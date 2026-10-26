from fastapi import APIRouter

from engine.storage import list_streams

router = APIRouter()


@router.get("")
def get_streams():
    """État de chaque flux (appareil + capteur) : catégorie, régime de détection (démarrage,
    référence, apprentissage, local), statut de la référence, échantillons locaux, silence."""
    return list_streams()
