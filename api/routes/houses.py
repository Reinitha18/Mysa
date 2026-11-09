from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.storage import (create_house, default_house_id, delete_house, get_house, list_device_meta, list_devices,
                            list_houses, update_house)

router = APIRouter()


class HouseIn(BaseModel):
    name: str = Field(max_length=60)
    address: str | None = Field(None, max_length=200)


class HousePatch(BaseModel):
    name: str | None = Field(None, max_length=60)
    address: str | None = Field(None, max_length=200)


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


@router.get("")
def get_houses():
    """Maisons, avec le nombre d'appareils de chacune (un appareil sans maison compte dans la première)."""
    meta, home = list_device_meta(), default_house_id()
    ids = {d["device_id"] for d in list_devices()} | set(meta)
    counts: dict[int, int] = {}
    for device_id in ids:
        house = (meta.get(device_id) or {}).get("house_id") or home
        counts[house] = counts.get(house, 0) + 1
    return [{**h, "device_count": counts.get(h["id"], 0)} for h in list_houses()]


@router.post("", status_code=201)
def post_house(body: HouseIn):
    name = _clean(body.name)
    if name is None:
        raise HTTPException(422, "Nom obligatoire")
    return {**create_house(name, _clean(body.address)), "device_count": 0}


@router.put("/{house_id}")
def put_house(house_id: int, body: HousePatch):
    if get_house(house_id) is None:
        raise HTTPException(404, f"Maison inconnue : {house_id}")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and _clean(changes["name"]) is None:
        raise HTTPException(422, "Nom obligatoire")
    return update_house(house_id, {k: _clean(v) for k, v in changes.items()})


@router.delete("/{house_id}")
def remove_house(house_id: int):
    """Supprime la maison. Ses appareils ne sont pas supprimés : ils passent à la première maison."""
    if get_house(house_id) is None:
        raise HTTPException(404, f"Maison inconnue : {house_id}")
    if len(list_houses()) <= 1:
        raise HTTPException(409, "Impossible de supprimer la dernière maison")
    delete_house(house_id)
    return {"deleted": house_id}
