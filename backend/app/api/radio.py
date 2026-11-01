from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from .. import radio
from ..models import User
from ..security import api_error, current_user

router = APIRouter()


@router.get("/radio/stations")
def stations(_: User = Depends(current_user)):
    """Korean radio stations, each with the regions it belongs to (radio.py)."""
    return {"regions": list(radio.REGIONS), "stations": [radio.station_out(s) for s in radio.STATIONS]}


@router.get("/radio/{station_id}/stream")
async def stream(station_id: str, _: User = Depends(current_user)):
    """The station, live, as one stream an <audio> element plays (relayed by this server)."""
    station = radio.BY_ID.get(station_id)
    if station is None:
        raise api_error(404, "not_found")
    try:
        body, media_type = await radio.relay(station)
    except radio.Busy:
        raise api_error(429, "radio_busy")
    except radio.Unavailable:
        raise api_error(502, "radio_unavailable")
    return StreamingResponse(body, media_type=media_type, headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
