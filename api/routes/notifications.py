"""État et test des notifications (engine/notify.py) depuis le dashboard : quels canaux sont
renseignés dans .env, et envoi d'un message de test sur chacun avant la démonstration."""

import asyncio

from fastapi import APIRouter

from engine import notify

router = APIRouter()


@router.get("")
def get_notifications():
    return {"enabled": notify.enabled(), "channels": notify.configured()}


@router.post("/test")
async def test_notifications():
    """Envoie un message de test sur chaque canal ; renvoie le résultat de chacun."""
    return {"enabled": notify.enabled(), "results": await asyncio.to_thread(notify.send_test)}
