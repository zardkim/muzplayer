"""Per-user data: playlists (and smart ones), liked songs, play history and counts.
Always scoped to the session user."""

import asyncio
import urllib.parse

from fastapi import APIRouter, Depends, Query, Request, Response
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import playlist_import
from ..config import settings
from ..db import get_db
from ..models import Album, Favorite, PlayCount, PlayHistory, Playlist, PlaylistMissing, PlaylistTrack, Track, User
from ..security import api_error, current_user
from ..smart import Rules
from .library import track_out, track_query
from .taste import forget_snapshots, load_tracks, smart_playlist_ids

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


DEFAULT_NAMES = {"ko": "기본 재생목록", "en": "My playlist"}


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
        "sort_order": p.sort_order,
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
    shared: bool | None = None  # everyone sees it (my own manual lists, not the default one)


class TrackIdsIn(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=1000)


class OrderIn(BaseModel):
    entry_ids: list[int]


class ListOrderIn(BaseModel):
    playlist_ids: list[int] = Field(max_length=10_000)


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
def shared_playlists(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
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
    return {"items": [{**playlist_out(p, c), "cover": covers.get(p.id), "owner": who, "can_edit": can_edit(user, p)} for p, c, who in rows]}


@router.put("/playlists/order", status_code=204)
def order_playlists(body: ListOrderIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """My playlists in my own order (the playlists page's "my order"); others' are left alone."""
    mine = {p.id: p for p in db.scalars(select(Playlist).where(Playlist.user_id == user.id, Playlist.id.in_(body.playlist_ids)))}
    for place, pid in enumerate(body.playlist_ids):
        if pid in mine:
            mine[pid].sort_order = place
    db.commit()


@router.post("/playlists", status_code=201)
def create_playlist(body: PlaylistIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = Playlist(user_id=user.id, name=body.name.strip())
    if body.rules is not None:
        playlist.kind, playlist.rules = "smart", body.rules.model_dump()
    db.add(playlist)
    db.commit()
    return playlist_out(playlist, None if playlist.kind == "smart" else 0)


@router.post("/playlists/import")
async def import_playlist(
    request: Request,
    name: str = Query("", max_length=300),
    create: bool = False,
    target_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """A playlist file from another player (.m3u, .m3u8, .pls; the request body as it is) matched to
    the library's songs (playlist_import.py): each entry with how it was found, or missing. With
    create, a new playlist (`name`: the file's, or as changed) of the songs found, in the file's order,
    or (target_id) they are added at the end of one of mine. The entries not found (missing, or
    several songs alike) are kept with it, to be looked for again after each scan."""
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > playlist_import.MAX_BYTES:
            raise api_error(413, "playlist_file_too_large")
    return await asyncio.to_thread(_import, db, user, raw, name, create, target_id)


def _import(db: Session, user: User, raw: bytes, name: str, create: bool, target_id: int | None) -> dict:
    entries = playlist_import.parse(playlist_import.decode(raw))
    if not entries:
        raise api_error(400, "playlist_file_empty")
    lib = playlist_import.Library(db)
    found = [(e, *playlist_import.match(lib, e)) for e in entries]
    ids = [song.id for _, _, song in found if song]
    tracks = {t.id: t for t in db.scalars(select(Track).where(Track.id.in_(ids)))} if ids else {}
    out = {
        "name": name.strip()[:200] or "playlist",
        "total": len(found),
        "found": len(ids),
        "items": [
            {
                "path": e.path,
                "label": e.title or playlist_import.file_name(e.path),
                "how": how,
                "track": {"id": song.id, "title": tracks[song.id].title, "artist": tracks[song.id].artist_text, "path": tracks[song.id].file_path} if song else None,
            }
            for e, how, song in found
        ],
    }
    if create:
        if target_id is not None:
            playlist = own_playlist(db, user, target_id)
            if playlist.kind == "smart":
                raise api_error(400, "smart_playlist")
        elif not ids:
            raise api_error(400, "playlist_file_no_match")
        else:
            playlist = Playlist(user_id=user.id, name=out["name"])
            db.add(playlist)
            db.flush()
        added, skipped = _append(db, playlist, ids)
        kept = 0
        for place, (e, how, song) in enumerate(found):
            if song is None and how in ("missing", "ambiguous"):
                db.add(PlaylistMissing(playlist_id=playlist.id, position=place, path=e.path, label=e.title, duration=e.duration))
                kept += 1
        db.commit()
        out |= {"playlist_id": playlist.id, "added": added, "skipped": skipped, "kept_missing": kept}
    return out


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or not (playlist.is_shared or playlist.user_id == user.id):
        raise api_error(404, "not_found")
    editable = {"can_edit": can_edit(user, playlist)}
    if playlist.kind == "smart":
        # worked out from the rules (now, or when last refreshed); entries have no entry_id (nothing to remove or move)
        ids, made = smart_playlist_ids(db, playlist, user)
        entries = [{"entry_id": None, "track": t} for t in load_tracks(db, user.id, ids)]
        return {**playlist_out(playlist, len(entries)), **editable, "entries": entries, "made_at": made}
    rows = db.execute(
        track_query(user.id)
        .add_columns(PlaylistTrack.id)
        .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
        .where(PlaylistTrack.playlist_id == playlist.id)
        .order_by(PlaylistTrack.position, PlaylistTrack.id)
    ).all()
    entries = [{"entry_id": r[-1], "track": track_out(r[:-1])} for r in rows]
    missing = db.scalars(select(PlaylistMissing).where(PlaylistMissing.playlist_id == playlist.id).order_by(PlaylistMissing.position, PlaylistMissing.id))
    return {
        **playlist_out(playlist, len(entries)),
        **editable,
        "entries": entries,
        "missing": [{"id": m.id, "path": m.path, "label": m.label or playlist_import.file_name(m.path)} for m in missing],
    }


@router.get("/playlists/{playlist_id}/export")
def export_playlist(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """The playlist as an .m3u8 file (UTF-8): each song's artist, title and length, and its path
    in the music library (other players read it relative to where the file is put)."""
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or not (playlist.is_shared or playlist.user_id == user.id):
        raise api_error(404, "not_found")
    if playlist.kind == "smart":
        ids = smart_playlist_ids(db, playlist, user)[0]  # the songs on screen
    else:
        ids = list(db.scalars(select(PlaylistTrack.track_id).where(PlaylistTrack.playlist_id == playlist.id).order_by(PlaylistTrack.position, PlaylistTrack.id)))
    tracks = {t.id: t for t in db.scalars(select(Track).where(Track.id.in_(ids)))} if ids else {}
    lines = ["#EXTM3U", f"#PLAYLIST:{playlist.name}"]
    for tid in ids:
        t = tracks.get(tid)
        if t is None:
            continue
        who = f"{t.artist_text} - " if t.artist_text else ""
        lines += [f"#EXTINF:{round(t.duration or -1)},{who}{t.title}", t.file_path]
    name = f"{playlist.name}.m3u8"
    quoted = urllib.parse.quote(name)
    return Response(
        "\n".join(lines) + "\n",
        media_type="audio/x-mpegurl; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"playlist.m3u8\"; filename*=UTF-8''{quoted}"},
    )


@router.post("/playlists/{playlist_id}/missing/rematch")
def rematch_missing(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """The songs of an imported file not found before, looked for again now: {"found", "left"}."""
    playlist = own_playlist(db, user, playlist_id)
    return playlist_import.rematch(db, [playlist.id])


@router.delete("/playlists/{playlist_id}/missing/{missing_id}", status_code=204)
def forget_missing(playlist_id: int, missing_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = own_playlist(db, user, playlist_id)
    db.execute(delete(PlaylistMissing).where(PlaylistMissing.id == missing_id, PlaylistMissing.playlist_id == playlist.id))
    db.commit()


@router.delete("/playlists/{playlist_id}/missing", status_code=204)
def forget_all_missing(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = own_playlist(db, user, playlist_id)
    db.execute(delete(PlaylistMissing).where(PlaylistMissing.playlist_id == playlist.id))
    db.commit()


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
        if body.rules.model_dump() != playlist.rules:
            forget_snapshots(db, [playlist.id])  # picked again by the new rules
        playlist.rules = body.rules.model_dump()
    if body.shared is not None and body.shared != playlist.is_shared:
        # a smart list's songs are worked out for whoever opens it (their likes, their plays): not shared
        if body.shared and (playlist.kind == "smart" or playlist.is_default or playlist.user_id != user.id):
            raise api_error(400, "cannot_share")
        playlist.is_shared = body.shared
    db.commit()
    if playlist.kind == "smart":
        return playlist_out(playlist, None)
    count = db.scalar(select(func.count()).where(PlaylistTrack.playlist_id == playlist.id))
    return playlist_out(playlist, count)


@router.post("/playlists/{playlist_id}/refresh", status_code=204)
def refresh_playlist(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """A smart playlist's songs picked again now (one kept for a day or a week, or a random one)."""
    playlist = own_playlist(db, user, playlist_id)
    if playlist.kind != "smart":
        raise api_error(400, "not_smart")
    forget_snapshots(db, [playlist.id])
    db.commit()


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
    added, skipped = _append(db, playlist, body.track_ids)
    db.commit()
    return {"added": added, "skipped": skipped}


def _append(db: Session, playlist: Playlist, track_ids: list[int]) -> tuple[int, int]:
    """Adds these songs at the end, those not in the list yet: (added, skipped)."""
    valid = set(db.scalars(select(Track.id).where(Track.id.in_(track_ids))))
    there = set(db.scalars(select(PlaylistTrack.track_id).where(PlaylistTrack.playlist_id == playlist.id)))
    position = db.scalar(
        select(func.coalesce(func.max(PlaylistTrack.position), -1)).where(PlaylistTrack.playlist_id == playlist.id)
    )
    added = skipped = 0
    for track_id in track_ids:
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
    return added, skipped


class TransferIn(BaseModel):
    target_id: int
    entry_ids: list[int] | None = Field(None, max_length=20_000)  # None: every song of the list
    mode: Literal["copy", "move"] = "copy"


@router.post("/playlists/{playlist_id}/transfer")
def transfer_tracks(
    playlist_id: int, body: TransferIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
):
    """Copies or moves songs of one of my playlists into another (at its end, those not there yet;
    moved ones leave this list, those the other already had too): {"added", "skipped", "removed"}."""
    source, target = own_playlist(db, user, playlist_id), own_playlist(db, user, body.target_id)
    if source.id == target.id:
        raise api_error(400, "same_playlist")
    if "smart" in (source.kind, target.kind):
        raise api_error(400, "smart_playlist")
    query = select(PlaylistTrack).where(PlaylistTrack.playlist_id == source.id).order_by(PlaylistTrack.position)
    if body.entry_ids is not None:
        query = query.where(PlaylistTrack.id.in_(body.entry_ids))
    entries = list(db.scalars(query))
    added, skipped = _append(db, target, [e.track_id for e in entries])
    removed = 0
    if body.mode == "move" and entries:
        removed = db.execute(delete(PlaylistTrack).where(PlaylistTrack.id.in_([e.id for e in entries]))).rowcount
        source.updated_at = func.now()
    db.commit()
    return {"added": added, "skipped": skipped, "removed": removed}


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
