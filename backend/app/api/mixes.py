"""Mixes: ready-made smart lists every user has (random 100, on repeat, most played, ...)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Album, Track, User
from ..security import api_error, current_user
from ..smart import MIX_KEYS, mix_preview, mix_query, radio_ids
from .library import track_out, track_query

router = APIRouter()


@router.get("/mixes")
def list_mixes(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """The mixes this user has songs for, with up to four covers each. Empty ones are left out
    (no ratings yet: no "top rated")."""
    items = []
    for key in MIX_KEYS:
        count, covers = mix_preview(db, key, user.id)
        if count:
            items.append({"key": key, "track_count": count, "cover_albums": covers})
    return {"items": items}


@router.get("/mixes/{key}")
def get_mix(key: str, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """The songs, worked out now: a random mix is new each time it is opened."""
    query = mix_query(key, track_query(user.id), user.id)
    if query is None:
        raise api_error(404, "not_found")
    return {"key": key, "tracks": [track_out(r) for r in db.execute(query)]}


@router.get("/radio")
def radio(
    track_id: int,
    exclude: str = Query("", max_length=4000),  # ids already in the queue, comma separated
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """Songs like this one: for "start radio" and for playing on when the queue runs out."""
    seed = db.get(Track, track_id)
    if seed is None:
        raise api_error(404, "not_found")
    seed_year = db.scalar(select(Album.year).where(Album.id == seed.album_id)) if seed.album_id else None
    skip = [int(x) for x in exclude.split(",") if x.strip().isdigit()][:500]
    ids = list(db.scalars(radio_ids(seed, seed_year, user.id, skip, limit)))
    if not ids:  # nothing in common with anything (an untagged song): any songs, still scored
        ids = list(db.scalars(radio_ids(seed, seed_year, user.id, skip, limit, related=False)))
    rows = {r[0].id: track_out(r) for r in db.execute(track_query(user.id).where(Track.id.in_(ids)))} if ids else {}
    return {"tracks": [rows[i] for i in ids if i in rows]}
