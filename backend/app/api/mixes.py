"""Mixes: ready-made smart lists every user has (random 100, on repeat, most played, ...)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import api_error, current_user
from ..smart import MIX_KEYS, mix_preview, mix_query
from .library import track_out, track_query

router = APIRouter()


@router.get("/mixes")
def list_mixes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The mixes this user has songs for, with up to four covers each. Empty ones are left out
    (no ratings yet: no "top rated")."""
    items = []
    for key in MIX_KEYS:
        count, covers = mix_preview(db, key, user.id)
        if count:
            items.append({"key": key, "track_count": count, "cover_albums": covers})
    return {"items": items}


@router.get("/mixes/{key}")
def get_mix(key: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The songs, worked out now: a random mix is new each time it is opened."""
    query = mix_query(key, track_query(user.id), user.id)
    if query is None:
        raise api_error(404, "not_found")
    return {"key": key, "tracks": [track_out(r) for r in db.execute(query)]}
