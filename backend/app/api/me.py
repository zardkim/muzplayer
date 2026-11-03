"""Per-user data: playlists (and smart ones), liked songs, play history and counts.
Always scoped to the session user."""

from fastapi import APIRouter, Depends, Query
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import ai_playlist
from ..ai_banner import AiError
from ..config import settings
from ..db import get_db
from ..models import Album, Favorite, PlayCount, PlayHistory, Playlist, PlaylistTrack, Track, User
from ..security import api_error, current_user
from ..smart import Rules, apply_rules
from .library import track_out, track_query

router = APIRouter()

HISTORY_KEEP = 1000


def own_playlist(db: Session, user: User, playlist_id: int) -> Playlist:
    """A playlist this person may change: their own, or (an admin) a shared one."""
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or not can_edit(user, playlist):
        raise api_error(404, "not_found")
    return playlist


def can_edit(user: User, playlist: Playlist) -> bool:
    return playlist.user_id == user.id or (playlist.is_shared and user.is_admin)


DEFAULT_NAMES = {"ko": "기본 플레이리스트", "en": "My playlist"}


def ensure_default(db: Session, model, user: User, names: dict[str, str]) -> None:
    """Gives the person their default list (a playlist or a video playlist) the first time."""
    if db.scalar(select(model.id).where(model.user_id == user.id, model.is_default)) is not None:
        return
    db.add(model(user_id=user.id, name=names.get(settings.default_locale, names["en"]), is_default=True))
    try:
        db.commit()
    except IntegrityError:  # made by another request meanwhile
        db.rollback()


def playlist_out(p: Playlist, track_count: int | None) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "kind": p.kind,
        "is_default": p.is_default,
        "is_shared": p.is_shared,
        "chart_id": p.chart_id,
        "rules": p.rules,
        "track_count": track_count,  # None for a smart playlist: known once it is opened
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


# a name: spaces around it dropped, then something must be left
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PlaylistIn(BaseModel):
    name: Name
    rules: Rules | None = None  # given: a smart playlist


class PlaylistPatch(BaseModel):
    name: Name | None = None
    rules: Rules | None = None  # smart playlists only


class TrackIdsIn(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=1000)


class OrderIn(BaseModel):
    entry_ids: list[int]


@router.get("/playlists")
def list_playlists(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    ensure_default(db, Playlist, user, DEFAULT_NAMES)
    rows = db.execute(
        select(Playlist, func.count(PlaylistTrack.id))
        .outerjoin(PlaylistTrack, PlaylistTrack.playlist_id == Playlist.id)
        .where(Playlist.user_id == user.id, Playlist.is_shared.is_(False))  # shared ones: their own row
        .group_by(Playlist.id)
        .order_by(Playlist.is_default.desc(), Playlist.updated_at.desc())
    )
    rows = rows.all()
    covers = first_covers(db, [p.id for p, _ in rows])
    return {"items": [{**playlist_out(p, None if p.kind == "smart" else c), "cover": covers.get(p.id)} for p, c in rows]}


def first_covers(db: Session, playlist_ids: list[int]) -> dict[int, dict]:
    """A cover for each list's card (home screen): its first song's album that has one."""
    if not playlist_ids:
        return {}
    first = (
        select(PlaylistTrack.playlist_id, Album.id, Album.cover_version)
        .join(Track, Track.id == PlaylistTrack.track_id)
        .join(Album, Album.id == Track.album_id)
        .where(PlaylistTrack.playlist_id.in_(playlist_ids), Album.cover_path.is_not(None))
        .order_by(PlaylistTrack.playlist_id, PlaylistTrack.position)
        .distinct(PlaylistTrack.playlist_id)
    )
    return {pid: {"id": aid, "v": v} for pid, aid, v in db.execute(first)}


@router.get("/playlists/shared")
def shared_playlists(_: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """Everyone's shared playlists (charts & themes page, home), newest first, with who made each."""
    rows = db.execute(
        select(Playlist, func.count(PlaylistTrack.id), User.display_name)
        .outerjoin(PlaylistTrack, PlaylistTrack.playlist_id == Playlist.id)
        .join(User, User.id == Playlist.user_id)
        .where(Playlist.is_shared.is_(True))
        .group_by(Playlist.id, User.display_name)
        .order_by(Playlist.created_at.desc())
    ).all()
    covers = first_covers(db, [p.id for p, _, _ in rows])
    return {"items": [{**playlist_out(p, c), "cover": covers.get(p.id), "owner": who} for p, c, who in rows]}


@router.post("/playlists", status_code=201)
def create_playlist(body: PlaylistIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = Playlist(user_id=user.id, name=body.name.strip())
    if body.rules is not None:
        playlist.kind, playlist.rules = "smart", body.rules.model_dump()
    db.add(playlist)
    db.commit()
    return playlist_out(playlist, None if playlist.kind == "smart" else 0)


class AiPlaylistIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=300)


@router.post("/playlists/ai")
def ai_playlist_draft(body: AiPlaylistIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """A smart playlist drafted from a sentence (ai_playlist.py): {"name", "rules", "count"}; not
    saved. 400 with a code when there is nothing usable (ai_no_rules, ai_no_songs)."""
    try:
        draft = ai_playlist.make(db, user.id, body.prompt.strip())
    except AiError as exc:
        raise api_error(503 if str(exc) in ("ai_unreachable", "ai_quota") else 400, str(exc)) from None
    rules = Rules.model_validate(draft["rules"])
    count = db.scalar(select(func.count()).select_from(apply_rules(track_query(user.id), rules, user.id).subquery()))
    if not count:
        raise api_error(400, "ai_no_songs")
    return {**draft, "count": count}


def smart_rules(playlist: Playlist) -> Rules | None:
    try:
        return Rules.model_validate(playlist.rules or {})
    except ValidationError:  # rules this version can't read: show nothing rather than fail
        return None


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or not (playlist.is_shared or playlist.user_id == user.id):
        raise api_error(404, "not_found")
    editable = {"can_edit": can_edit(user, playlist)}
    if playlist.kind == "smart":
        # worked out now from the rules; entries have no entry_id (nothing to remove or move)
        rules = smart_rules(playlist)
        rows = db.execute(apply_rules(track_query(user.id), rules, user.id)).all() if rules else []
        entries = [{"entry_id": None, "track": track_out(r)} for r in rows]
        return {**playlist_out(playlist, len(entries)), **editable, "entries": entries}
    rows = db.execute(
        track_query(user.id)
        .add_columns(PlaylistTrack.id)
        .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
        .where(PlaylistTrack.playlist_id == playlist.id)
        .order_by(PlaylistTrack.position, PlaylistTrack.id)
    ).all()
    entries = [{"entry_id": r[-1], "track": track_out(r[:-1])} for r in rows]
    return {**playlist_out(playlist, len(entries)), **editable, "entries": entries}


@router.patch("/playlists/{playlist_id}")
def update_playlist(
    playlist_id: int, body: PlaylistPatch, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
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
def delete_playlist(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = own_playlist(db, user, playlist_id)
    if playlist.is_default:
        raise api_error(400, "default_playlist")  # everyone keeps theirs
    db.delete(playlist)
    db.commit()


@router.post("/playlists/{playlist_id}/tracks")
def add_tracks(
    playlist_id: int, body: TrackIdsIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
):
    playlist = own_playlist(db, user, playlist_id)
    if playlist.kind == "smart":
        raise api_error(400, "smart_playlist")  # its songs come from its rules
    """Adds the songs not in the list yet: {"added": n, "skipped": songs already there}."""
    valid = set(db.scalars(select(Track.id).where(Track.id.in_(body.track_ids))))
    there = set(db.scalars(select(PlaylistTrack.track_id).where(PlaylistTrack.playlist_id == playlist.id)))
    position = db.scalar(
        select(func.coalesce(func.max(PlaylistTrack.position), -1)).where(PlaylistTrack.playlist_id == playlist.id)
    )
    added = skipped = 0
    for track_id in body.track_ids:
        if track_id not in valid:
            continue
        if track_id in there:
            skipped += 1
            continue
        there.add(track_id)
        position += 1
        added += 1
        db.add(PlaylistTrack(playlist_id=playlist.id, track_id=track_id, position=position))
    playlist.updated_at = func.now()
    db.commit()
    return {"added": added, "skipped": skipped}


@router.delete("/playlists/{playlist_id}/tracks/{entry_id}", status_code=204)
def remove_track(
    playlist_id: int, entry_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
):
    playlist = own_playlist(db, user, playlist_id)
    db.execute(delete(PlaylistTrack).where(PlaylistTrack.id == entry_id, PlaylistTrack.playlist_id == playlist.id))
    playlist.updated_at = func.now()
    db.commit()


@router.put("/playlists/{playlist_id}/order", status_code=204)
def reorder(playlist_id: int, body: OrderIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = own_playlist(db, user, playlist_id)
    entries = {e.id: e for e in db.scalars(select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist.id))}
    if set(body.entry_ids) != set(entries) or len(body.entry_ids) != len(entries):
        raise api_error(400, "invalid_order")
    for position, entry_id in enumerate(body.entry_ids):
        entries[entry_id].position = position
    playlist.updated_at = func.now()
    db.commit()


@router.get("/favorites")
def list_favorites(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    rows = db.execute(
        track_query(user.id)
        .join(Favorite, (Favorite.track_id == Track.id) & (Favorite.user_id == user.id))
        .order_by(Favorite.created_at.desc())
    )
    return {"items": [track_out(r) for r in rows]}


@router.put("/favorites/{track_id}", status_code=204)
def add_favorite(track_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    if db.get(Track, track_id) is None:
        raise api_error(404, "not_found")
    if db.get(Favorite, (user.id, track_id)) is None:
        db.add(Favorite(user_id=user.id, track_id=track_id))
        db.commit()


@router.delete("/favorites/{track_id}", status_code=204)
def remove_favorite(track_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.track_id == track_id))
    db.commit()


class HistoryIn(BaseModel):
    track_id: int


@router.get("/history")
def list_history(
    limit: int = Query(100, ge=1, le=HISTORY_KEEP),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
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
def add_history(body: HistoryIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    if db.get(Track, body.track_id) is None:
        raise api_error(404, "not_found")
    if not user.record_history:  # listening privately: no history, no play count
        return
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
