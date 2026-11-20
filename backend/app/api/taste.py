"""Smart playlists made with the wizard: each user's taste (users.taste, smart.Taste), what the
wizard suggests and counts while it asks, and a smart playlist's songs as kept for a while
(smart_snapshots, rules.refresh). Always the session user's own."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Artist, Favorite, Genre, PlayCount, Playlist, SmartSnapshot, Track, TrackGenre, User
from ..security import api_error, current_user
from ..smart import Rules, Taste, matching_count, smart_ids
from .library import listed_tracks, shown_name, track_out, track_query

router = APIRouter()

REFRESH_AFTER = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
PREVIEW_SONGS = 8


def user_taste(user: User) -> Taste | None:
    try:
        return Taste.model_validate(user.taste) if user.taste else None
    except ValidationError:  # saved by a version that read it otherwise: as if not asked yet
        return None


def smart_rules(playlist: Playlist) -> Rules | None:
    try:
        return Rules.model_validate(playlist.rules or {})
    except ValidationError:  # rules this version can't read: show nothing rather than fail
        return None


def load_tracks(db: Session, user_id: int, ids: list[int]) -> list[dict]:
    """These songs (the listed ones) in this order, as lists show them."""
    if not ids:
        return []
    rows = {r[0].id: r for r in db.execute(track_query(user_id).where(Track.id.in_(ids), listed_tracks()))}
    return [track_out(rows[i]) for i in ids if i in rows]


def smart_playlist_ids(db: Session, playlist: Playlist, user: User) -> tuple[list[int], datetime | None]:
    """A smart playlist's songs for the person opening it, and when they were picked if kept for a while."""
    rules = smart_rules(playlist)
    if rules is None:
        return [], None
    keep = REFRESH_AFTER.get(rules.refresh)
    if keep is not None:
        snap = db.get(SmartSnapshot, playlist.id)
        if snap is not None and datetime.now(UTC) - snap.made_at < keep:
            # a song left out since is gone at once; the rest stay as picked
            out = set(taste.exclude_tracks) if rules.profile and (taste := user_taste(user)) else set()
            return [i for i in snap.track_ids if i not in out], snap.made_at
    ids = smart_ids(db, rules, user.id, user_taste(user) if rules.profile else None)
    if keep is None:
        return ids, None
    made = datetime.now(UTC)
    db.execute(
        insert(SmartSnapshot)
        .values(playlist_id=playlist.id, track_ids=ids, made_at=made)
        .on_conflict_do_update(index_elements=["playlist_id"], set_={"track_ids": ids, "made_at": made})
    )
    db.commit()
    return ids, made


def forget_snapshots(db: Session, playlist_ids: list[int]) -> None:
    if playlist_ids:
        db.execute(delete(SmartSnapshot).where(SmartSnapshot.playlist_id.in_(playlist_ids)))


def taste_out(db: Session, user: User) -> dict:
    """The taste with the names of the artists and songs it keeps by id (to show them)."""
    taste = user_taste(user)
    if taste is None:
        return {"taste": None, "artists": [], "tracks": []}
    ids = list({*taste.artists, *taste.exclude_artists})
    artists = [{"id": i, "name": n} for i, n in db.execute(select(Artist.id, shown_name()).where(Artist.id.in_(ids)))] if ids else []
    tracks = [
        {"id": t.id, "title": t.title, "artist": t.artist_text}
        for t in db.scalars(select(Track).where(Track.id.in_(taste.exclude_tracks)))
    ] if taste.exclude_tracks else []
    # artists and songs gone from the library since (pruned, purged) are left out of what it shows
    there, songs = {a["id"] for a in artists}, {t["id"] for t in tracks}
    shown = taste.model_copy(update={
        "artists": [i for i in taste.artists if i in there],
        "exclude_artists": [i for i in taste.exclude_artists if i in there],
        "exclude_tracks": [i for i in taste.exclude_tracks if i in songs],
    })
    return {"taste": shown.model_dump(), "artists": artists, "tracks": tracks}


def _profile_playlists(db: Session, user: User) -> list[int]:
    return [
        p.id for p in db.scalars(select(Playlist).where(Playlist.user_id == user.id, Playlist.kind == "smart"))
        if (p.rules or {}).get("profile")
    ]


def _save(db: Session, user: User, taste: Taste) -> None:
    before = user_taste(user)
    user.taste = taste.model_dump()
    # the lists made from it follow at once when what it asks for changed (a song left out or brought
    # back only drops from or joins the next pick: smart_playlist_ids leaves it out of a kept one)
    if before is None or before.model_dump(exclude={"exclude_tracks"}) != taste.model_dump(exclude={"exclude_tracks"}):
        forget_snapshots(db, _profile_playlists(db, user))
    db.commit()


@router.get("/taste")
def get_taste(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    return taste_out(db, user)


@router.put("/taste")
def put_taste(body: Taste, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    _save(db, user, body)
    return taste_out(db, user)


@router.post("/taste/exclude/{track_id}", status_code=204)
def exclude_track(track_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """This song never again in the smart playlists made from my taste (undone in settings)."""
    if db.get(Track, track_id) is None:
        raise api_error(404, "not_found")
    taste = user_taste(user) or Taste()
    if track_id not in taste.exclude_tracks:
        if len(taste.exclude_tracks) >= 5000:
            raise api_error(400, "taste_too_many")
        _save(db, user, taste.model_copy(update={"exclude_tracks": [*taste.exclude_tracks, track_id]}))


@router.delete("/taste/exclude/{track_id}", status_code=204)
def include_track(track_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    taste = user_taste(user)
    if taste is not None and track_id in taste.exclude_tracks:
        _save(db, user, taste.model_copy(update={"exclude_tracks": [t for t in taste.exclude_tracks if t != track_id]}))


@router.get("/taste/suggest")
def suggest(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """What the wizard offers first: the library's genres and artists, the ones this person plays and
    likes most first (the library's biggest when they have not played anything yet)."""
    plays = func.coalesce(func.sum(PlayCount.plays), 0) + func.count(Favorite.track_id) * 3
    mine = and_(PlayCount.track_id == Track.id, PlayCount.user_id == user.id)
    liked = and_(Favorite.track_id == Track.id, Favorite.user_id == user.id)
    genres = db.execute(
        select(Genre.name, func.count(func.distinct(Track.id)).label("n"), plays.label("mine"))
        .join(TrackGenre, TrackGenre.genre_id == Genre.id)
        .join(Track, and_(Track.id == TrackGenre.track_id, listed_tracks()))
        .outerjoin(PlayCount, mine)
        .outerjoin(Favorite, liked)
        .group_by(Genre.id)
        .order_by(desc("mine"), desc("n"), func.lower(Genre.name))
        .limit(60)
    ).all()
    artists = db.execute(
        select(Artist.id, shown_name(), func.count(func.distinct(Track.id)).label("n"), plays.label("mine"))
        .join(Track, and_(Track.artist_id == Artist.id, listed_tracks()))
        .outerjoin(PlayCount, mine)
        .outerjoin(Favorite, liked)
        .group_by(Artist.id)
        .order_by(desc("mine"), desc("n"), Artist.id)
        .limit(30)
    ).all()
    return {
        "genres": [{"name": name, "count": n, "mine": bool(m)} for name, n, m in genres],
        "artists": [{"id": i, "name": name, "count": n, "mine": bool(m)} for i, name, n, m in artists],
    }


class PreviewIn(BaseModel):
    rules: Rules
    taste: Taste | None = None  # the wizard's answers so far (not saved yet); none: the saved one


@router.post("/smart/preview")
def preview(body: PreviewIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """While the wizard asks: how many songs the answers let in, and the first few of the list."""
    taste = body.taste if body.taste is not None else user_taste(user)
    taste = taste if body.rules.profile else None
    ids = smart_ids(db, body.rules, user.id, taste)
    seconds = db.scalar(select(func.sum(Track.duration)).where(Track.id.in_(ids))) if ids else 0
    seed = db.get(Track, body.rules.seed) if body.rules.seed else None
    return {
        "seed": {"id": seed.id, "title": seed.title, "artist": seed.artist_text} if seed else None,
        "matching": matching_count(db, body.rules, user.id, taste),
        "count": len(ids),
        "minutes": round((seconds or 0) / 60),
        "tracks": load_tracks(db, user.id, ids[:PREVIEW_SONGS]),
    }
