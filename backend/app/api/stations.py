"""Stations (home): endless radios of different kinds. Each call gives the next songs, leaving out the
ones already in the queue (exclude), so the player asks again whenever the queue runs low:

- library: anything, at random
- hidden: songs this person has hardly played, their stars and likes first ("hidden gems")
- timetravel: a pass through the years, oldest first
- randomalbum: a whole album at random, in its order
- artist / album: an artist's (an album's) songs, then songs like them
- genre / decade: songs of one genre, of one decade
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Album, Favorite, PlayCount, Track, TrackGenre, TrackRating, User
from ..security import api_error, current_user
from ..smart import radio_ids, with_user_marks
from .library import listed_tracks, track_out, track_query

router = APIRouter()

KINDS = ("library", "hidden", "timetravel", "randomalbum", "artist", "album", "genre", "decade")


def _ids(db: Session, query) -> list[int]:
    return list(db.scalars(query))


@router.get("/stations/{kind}")
def station(
    kind: str,
    artist_id: int | None = None,
    album_id: int | None = None,
    genre_id: int | None = None,
    decade: int | None = Query(None, ge=1900, le=2100),
    exclude: str = Query("", max_length=8000),  # ids already in the queue, comma separated
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """The next songs of a station: {"tracks": [...]} (empty when it has nothing more)."""
    if kind not in KINDS:
        raise api_error(404, "not_found")
    skip = [int(x) for x in exclude.split(",") if x.strip().isdigit()][:1000]
    base = select(Track.id).outerjoin(Album, Album.id == Track.album_id).where(listed_tracks())
    if skip:
        base = base.where(Track.id.not_in(skip))

    ids: list[int] = []
    if kind == "library":
        ids = _ids(db, base.order_by(func.random()).limit(limit))
    elif kind == "hidden":
        # played once at most; first the ones this person starred or whose artist they like
        fav = select(Track.artist_id).join(Favorite, and_(Favorite.track_id == Track.id, Favorite.user_id == user.id))
        liked_artist = Track.artist_id.in_(fav.scalar_subquery())
        score = case((TrackRating.rating >= 7, 3), else_=0) + case((liked_artist, 2), else_=0) + func.random() * 3
        q = with_user_marks(base, user.id).where(func.coalesce(PlayCount.plays, 0) <= 1).order_by(score.desc()).limit(limit)
        ids = _ids(db, q)
    elif kind == "timetravel":
        # songs from across the years, then put in order of their year
        rows = db.execute(
            select(Track.id, Album.year).outerjoin(Album, Album.id == Track.album_id)
            .where(listed_tracks(), Album.year.is_not(None), *( [Track.id.not_in(skip)] if skip else []))
            .order_by(func.random()).limit(limit)
        ).all()
        ids = [i for i, _ in sorted(rows, key=lambda r: r[1])]
    elif kind == "randomalbum":
        # an album none of whose songs is in the queue yet, whole and in order
        played = select(Track.album_id).where(Track.id.in_(skip or [-1])).scalar_subquery()
        album = db.scalar(
            select(Album.id).where(Album.kind != "chart", Album.id.not_in(played),
                                   exists().where(Track.album_id == Album.id, listed_tracks()))
            .order_by(func.random()).limit(1)
        )
        if album:
            ids = _ids(db, select(Track.id).where(Track.album_id == album, listed_tracks())
                       .order_by(Track.disc_no.nulls_last(), Track.track_no.nulls_last(), Track.file_path))
    elif kind in ("artist", "album"):
        if (artist_id if kind == "artist" else album_id) is None:
            raise api_error(400, "missing_seed")
        own = (or_(Track.artist_id == artist_id, Album.album_artist_id == artist_id) if kind == "artist"
               else Track.album_id == album_id)
        ids = _ids(db, base.where(own).order_by(func.random()).limit(limit))
        if len(ids) < limit:
            # its own songs used up (or few): songs like one of them
            seed = db.scalar(select(Track).outerjoin(Album, Album.id == Track.album_id).where(own, listed_tracks()).order_by(func.random()).limit(1))
            if seed is not None:
                seed_year = db.scalar(select(Album.year).where(Album.id == seed.album_id)) if seed.album_id else None
                ids += _ids(db, radio_ids(seed, seed_year, user.id, skip + ids, limit - len(ids)))
                if len(ids) < limit:  # nothing in common with anything (untagged): any songs, still scored
                    ids += _ids(db, radio_ids(seed, seed_year, user.id, skip + ids, limit - len(ids), related=False))
    elif kind == "genre":
        if genre_id is None:
            raise api_error(400, "missing_seed")
        in_genre = exists().where(TrackGenre.track_id == Track.id, TrackGenre.genre_id == genre_id)
        ids = _ids(db, base.where(in_genre).order_by(func.random()).limit(limit))
    elif kind == "decade":
        if decade is None:
            raise api_error(400, "missing_seed")
        start = decade - decade % 10
        ids = _ids(db, base.where(Album.year.between(start, start + 9)).order_by(func.random()).limit(limit))

    rows = {r[0].id: track_out(r) for r in db.execute(track_query(user.id).where(Track.id.in_(ids)))} if ids else {}
    return {"tracks": [rows[i] for i in ids if i in rows]}


@router.get("/stations")
def station_options(_: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """What the pickers offer: the decades the library has songs from (newest first)."""
    years = db.scalars(
        select(func.distinct(func.floor(Album.year / 10) * 10))
        .join(Track, Track.album_id == Album.id)
        .where(Album.year.is_not(None), listed_tracks())
    )
    return {"decades": sorted({int(y) for y in years if y}, reverse=True)}

