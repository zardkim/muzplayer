import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import radio, radio_now
from ..db import get_db
from ..models import RadioCustom, User
from ..security import api_error, current_user

router = APIRouter()
CUSTOM_KEPT = 50  # stations one person may add


@router.get("/radio/stations")
def stations(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """Korean radio stations, each with the regions it belongs to (radio.py), then the ones this
    person added (region "custom")."""
    mine = db.scalars(select(RadioCustom).where(RadioCustom.user_id == user.id).order_by(RadioCustom.id))
    return {
        "regions": list(radio.REGIONS),
        "stations": [radio.station_out(s) for s in radio.STATIONS] + [radio.station_out(radio.custom_station(c)) for c in mine],
    }


@router.get("/radio/stations/{station_id}/now")
def on_air_now(station_id: str, _: User = Depends(current_user)):
    """The programme the station has on air now (radio_now.py): {"title", "start", "end"}, all null
    when the broadcaster doesn't say (or isn't asked)."""
    return radio_now.now(station_id) or {"title": None, "start": None, "end": None}


class CustomIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=2000)]


@router.post("/radio/custom")
async def add_custom(body: CustomIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """Adds a station by its address once it answers as a stream this server plays."""
    if len(db.scalars(select(RadioCustom.id).where(RadioCustom.user_id == user.id)).all()) >= CUSTOM_KEPT:
        raise api_error(400, "radio_too_many")
    db.commit()  # the station may take seconds to answer: don't hold a pool connection meanwhile
    try:
        url = await asyncio.to_thread(radio.probe, body.url)
    except radio.Unsupported:
        raise api_error(400, "radio_unsupported") from None
    except radio.Unavailable:
        raise api_error(400, "radio_unreachable") from None
    row = RadioCustom(user_id=user.id, name=body.name, url=url)
    db.add(row)
    db.commit()
    return radio.station_out(radio.custom_station(row))


@router.delete("/radio/custom/{custom_id}", status_code=204)
def delete_custom(custom_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    row = db.get(RadioCustom, custom_id)
    if row is None or row.user_id != user.id:
        raise api_error(404, "not_found")
    db.delete(row)
    db.commit()


def _station(db: Session, user: User, station_id: str) -> dict | None:
    if station_id in radio.BY_ID:
        return radio.BY_ID[station_id]
    if station_id.startswith("c") and station_id[1:].isdigit():
        row = db.get(RadioCustom, int(station_id[1:]))
        if row is not None and row.user_id == user.id:
            return radio.custom_station(row)
    return None


@router.get("/radio/{station_id}/stream")
async def stream(station_id: str, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """The station, live, as one stream an <audio> element plays (relayed by this server)."""
    station = _station(db, user, station_id)
    db.commit()  # a stream lasts hours: give the connection back now
    if station is None:
        raise api_error(404, "not_found")
    try:
        body, media_type = await radio.relay(station)
    except radio.Busy:
        raise api_error(429, "radio_busy") from None
    except radio.Unavailable:
        raise api_error(502, "radio_unavailable") from None
    return StreamingResponse(body, media_type=media_type, headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
