"""Per-user data: playlists (and smart ones), liked songs, play history and counts.
Always scoped to the session user."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Favorite, PlayCount, PlayHistory, Playlist, PlaylistTrack, Track, User
from ..security import api_error, current_user
from ..smart import Rules, apply_rules
from .library import track_out, track_query

router = APIRouter()

HISTORY_KEEP = 1000


def own_playlist(db: Session, user: User, playlist_id: int) -> Playlist:
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or playlist.user_id != user.id:
        raise api_error(404, "not_found")
    return playlist


def playlist_out(p: Playlist, track_count: int | None) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "kind": p.kind,
        "rules": p.rules,
        "track_count": track_count,  # None for a smart playlist: known once it is opened
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


class PlaylistIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rules: Rules | None = None  # given: a smart playlist


class PlaylistPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    rules: Rules | None = None  # smart playlists only


class TrackIdsIn(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=1000)


class OrderIn(BaseModel):
    entry_ids: list[int]


@router.get("/playlists")
def list_playlists(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Playlist, func.count(PlaylistTrack.id))
        .outerjoin(PlaylistTrack, PlaylistTrack.playlist_id == Playlist.id)
        .where(Playlist.user_id == user.id)
        .group_by(Playlist.id)
        .order_by(Playlist.updated_at.desc())
    )
    return {"items": [playlist_out(p, None if p.kind == "smart" else c) for p, c in rows]}


@router.post("/playlists", status_code=201)
def create_playlist(body: PlaylistIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    playlist = Playlist(user_id=user.id, name=body.name.strip())
    if body.rules is not None:
        playlist.kind, playlist.rules = "smart", body.rules.model_dump()
    db.add(playlist)
    db.commit()
    return playlist_out(playlist, None if playlist.kind == "smart" else 0)


def smart_rules(playlist: Playlist) -> Rules | None:
    try:
        return Rules.model_validate(playlist.rules or {})
    except ValidationError:  # rules this version can't read: show nothing rather than fail
        return None


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    playlist = own_playlist(db, user, playlist_id)
    if playlist.kind == "smart":
        # worked out now from the rules; entries have no entry_id (nothing to remove or move)
        rules = smart_rules(playlist)
        rows = db.execute(apply_rules(track_query(user.id), rules, user.id)).all() if rules else []
        entries = [{"entry_id": None, "track": track_out(r)} for r in rows]
        return {**playlist_out(playlist, len(entries)), "entries": entries}
    rows = db.execute(
        track_query(user.id)
        .add_columns(PlaylistTrack.id)
        .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
        .where(PlaylistTrack.playlist_id == playlist.id)
        .order_by(PlaylistTrack.position, PlaylistTrack.id)
    ).all()
    entries = [{"entry_id": r[-1], "track": track_out(r[:-1])} for r in rows]
    return {**playlist_out(playlist, len(entries)), "entries": entries}


@router.patch("/playlists/{playlist_id}")
def update_playlist(
    playlist_id: int, body: PlaylistPatch, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    playlist = own_playlist(db, user, playlist_id)
    if body.name is not None:
        playlist.name = body.name.strip()
    if body.rules is not None:
        if playlist.kind != "smart":
            raise api_error(400, "not_smart")
        playlist.rules = body.rules.model_dump()
    db.commit()
    if playlist.kind == "smart":
        return playlist_out(playlist, None)
    count = db.scalar(select(func.count()).where(PlaylistTrack.playlist_id == playlist.id))
    return playlist_out(playlist, count)


@router.delete("/playlists/{playlist_id}", status_code=204)
def delete_playlist(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(own_playlist(db, user, playlist_id))
    db.commit()


@router.post("/playlists/{playlist_id}/tracks", status_code=204)
def add_tracks(
    playlist_id: int, body: TrackIdsIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    playlist = own_playlist(db, user, playlist_id)
    if playlist.kind == "smart":
        raise api_error(400, "smart_playlist")  # its songs come from its rules
    valid = set(db.scalars(select(Track.id).where(Track.id.in_(body.track_ids))))
    position = db.scalar(
        select(func.coalesce(func.max(PlaylistTrack.position), -1)).where(PlaylistTrack.playlist_id == playlist.id)
    )
    for track_id in body.track_ids:
        if track_id in valid:
            position += 1
            db.add(PlaylistTrack(playlist_id=playlist.id, track_id=track_id, position=position))
    playlist.updated_at = func.now()
    db.commit()


@router.delete("/playlists/{playlist_id}/tracks/{entry_id}", status_code=204)
def remove_track(
    playlist_id: int, entry_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    playlist = own_playlist(db, user, playlist_id)
    db.execute(delete(PlaylistTrack).where(PlaylistTrack.id == entry_id, PlaylistTrack.playlist_id == playlist.id))
    playlist.updated_at = func.now()
    db.commit()


@router.put("/playlists/{playlist_id}/order", status_code=204)
def reorder(playlist_id: int, body: OrderIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    playlist = own_playlist(db, user, playlist_id)
    entries = {e.id: e for e in db.scalars(select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist.id))}
    if set(body.entry_ids) != set(entries) or len(body.entry_ids) != len(entries):
        raise api_error(400, "invalid_order")
    for position, entry_id in enumerate(body.entry_ids):
        entries[entry_id].position = position
    playlist.updated_at = func.now()
    db.commit()


@router.get("/favorites")
def list_favorites(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        track_query(user.id)
        .join(Favorite, (Favorite.track_id == Track.id) & (Favorite.user_id == user.id))
        .order_by(Favorite.created_at.desc())
    )
    return {"items": [track_out(r) for r in rows]}


@router.put("/favorites/{track_id}", status_code=204)
def add_favorite(track_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Track, track_id) is None:
        raise api_error(404, "not_found")
    if db.get(Favorite, (user.id, track_id)) is None:
        db.add(Favorite(user_id=user.id, track_id=track_id))
        db.commit()


@router.delete("/favorites/{track_id}", status_code=204)
def remove_favorite(track_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.track_id == track_id))
    db.commit()


class HistoryIn(BaseModel):
    track_id: int


@router.get("/history")
def list_history(
    limit: int = Query(100, ge=1, le=HISTORY_KEEP),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        track_query(user.id)
        .add_columns(PlayHistory.played_at)
        .join(PlayHistory, PlayHistory.track_id == Track.id)
        .where(PlayHistory.user_id == user.id)
        .order_by(PlayHistory.played_at.desc(), PlayHistory.id.desc())
        .limit(limit)
    ).all()
    return {"items": [{**track_out(r[:-1]), "played_at": r[-1]} for r in rows]}


@router.post("/history", status_code=204)
def add_history(body: HistoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Track, body.track_id) is None:
        raise api_error(404, "not_found")
    db.add(PlayHistory(user_id=user.id, track_id=body.track_id))
    # the count is kept for good; the history below keeps only the latest plays
    db.execute(
        insert(PlayCount)
        .values(user_id=user.id, track_id=body.track_id, plays=1, last_played_at=func.now())
        .on_conflict_do_update(
            index_elements=["user_id", "track_id"],
            set_={"plays": PlayCount.plays + 1, "last_played_at": func.now()},
        )
    )
    db.flush()
    keep = (
        select(PlayHistory.id)
        .where(PlayHistory.user_id == user.id)
        .order_by(PlayHistory.played_at.desc(), PlayHistory.id.desc())
        .limit(HISTORY_KEEP)
    )
    db.execute(delete(PlayHistory).where(PlayHistory.user_id == user.id, PlayHistory.id.not_in(keep)))
    db.commit()
