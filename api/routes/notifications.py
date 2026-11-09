"""État, configuration et test des notifications (engine/notify.py) depuis le dashboard : quels canaux
sont renseignés (.env ou Paramètres), modification de leurs réglages, et envoi d'un message de test."""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from engine import notify

router = APIRouter()


class NotificationSettings(BaseModel):
    smtp_host: str | None = Field(None, max_length=200)
    smtp_port: str | None = Field(None, max_length=5)
    smtp_user: str | None = Field(None, max_length=200)
    smtp_password: str | None = Field(None, max_length=200)
    smtp_from: str | None = Field(None, max_length=200)
    smtp_to: str | None = Field(None, max_length=300)
    sms_url: str | None = Field(None, max_length=300)
    sms_user: str | None = Field(None, max_length=200)
    sms_password: str | None = Field(None, max_length=200)
    sms_to: str | None = Field(None, max_length=100)


@router.get("")
def get_notifications():
    return {"enabled": notify.enabled(), "channels": notify.configured()}


@router.get("/settings")
def get_settings():
    """Réglages affichables dans Paramètres. Les mots de passe ne sont jamais renvoyés : seulement un
    booléen indiquant si l'un d'eux (base ou .env) est déjà renseigné."""
    return notify.get_settings()


@router.put("/settings")
def put_settings(body: NotificationSettings):
    """Enregistre les champs fournis. Un champ texte vide efface la valeur stockée (retour au .env s'il y
    en a un) ; un mot de passe laissé vide garde celui déjà enregistré, pour ne pas avoir à le ressaisir
    à chaque modification d'un autre champ."""
    notify.save_settings(body.model_dump())
    return notify.get_settings()


@router.post("/test")
async def test_notifications():
    """Envoie un message de test sur chaque canal ; renvoie le résultat de chacun."""
    return {"enabled": notify.enabled(), "results": await asyncio.to_thread(notify.send_test)}
