"""Music videos: YouTube videos of albums and songs, and video files on the NAS (library/video).
Anyone may add one; the person who added it or an admin may change or remove it."""

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from .. import youtube
from ..config import settings
from ..db import get_db
from ..models import Album, Artist, Track, User, Video, VideoPlaylist, VideoPlaylistItem
from ..security import api_error, current_user

router = APIRouter()

KINDS = ("mv", "concert", "tv", "fan", "other")
Kind = Literal["mv", "concert", "tv", "fan", "other"]
# what browsers play in <video> (mkv/mov only when their codecs are H.264/AAC, the usual case)
VIDEO_EXTS = {".mp4", ".m4v", ".webm", ".mov", ".mkv", ".ogv"}
VIDEO_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
               ".mkv": "video/x-matroska", ".ogv": "video/ogg"}


def video_out(v: Video, user: User) -> dict:
    return {
        "id": v.id,
        "source": "file" if v.file_path else "youtube",
        "youtube_id": v.youtube_id,
        "file_path": v.file_path,
        "kind": v.kind,
        "title": v.title,
        "channel": v.channel,
        "album_id": v.album_id,
        "track_id": v.track_id,
        "can_edit": user.is_admin or v.added_by == user.id,
        "created_at": v.created_at,
    }


def _list(db: Session, user: User, **target) -> dict:
    (column, value), = target.items()
    rows = db.scalars(
        select(Video).where(getattr(Video, column) == value).order_by(Video.position, Video.id)
    )
    return {"items": [video_out(v, user) for v in rows]}


_album_of_track = aliased(Album)


def _listing(*extra):
    """Videos with their song or album, for lists (Music videos page, search, video playlists)."""
    return (
        select(
            Video, Track.title, Track.artist_text, Track.album_id, _album_of_track.cover_path,
            _album_of_track.cover_version, Album.title, Artist.name, Album.cover_path, Album.cover_version, *extra,
        )
        .outerjoin(Track, Track.id == Video.track_id)
        .outerjoin(_album_of_track, _album_of_track.id == Track.album_id)
        .outerjoin(Album, Album.id == Video.album_id)
        .outerjoin(Artist, Artist.id == Album.album_artist_id)
    )


def list_item(row, user: User) -> dict:
    v, t_title, t_artist, t_album, t_cover, t_cover_v, a_title, a_artist, a_cover, a_cover_v = row[:10]
    if v.track_id is None and v.album_id is None:
        target = None
    elif v.track_id is not None:
        target = {"type": "track", "title": t_title, "artist": t_artist or "", "album_id": t_album,
                  "has_cover": bool(t_cover), "cover_v": t_cover_v if t_cover else 0}
    else:
        target = {"type": "album", "title": a_title, "artist": a_artist or "", "album_id": v.album_id,
                  "has_cover": bool(a_cover), "cover_v": a_cover_v if a_cover else 0}
    return {**video_out(v, user), "target": target}


def _matches(q: str):
    """Search: the video's title or channel, the song or album it belongs to, its artist, or the file's path."""
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return or_(
        Video.title.ilike(pattern), Video.channel.ilike(pattern), Video.file_path.ilike(pattern),
        Track.title.ilike(pattern), Track.artist_text.ilike(pattern), Album.title.ilike(pattern), Artist.name.ilike(pattern),
    )


@router.get("/videos")
def all_videos(
    kind: Kind | None = None,
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """Every video added (the Music videos page; with q, the search), YouTube and NAS files, newest
    first, each with its song or album (a NAS file may have none)."""
    cond = [Video.kind == kind] if kind else []
    if q.strip():
        cond.append(_matches(q.strip()))
    total = db.scalar(select(func.count()).select_from(_listing().where(*cond).subquery()))
    rows = db.execute(_listing().where(*cond).order_by(Video.created_at.desc(), Video.id.desc()).offset(offset).limit(limit))
    return {"items": [list_item(r, user) for r in rows], "total": total}


@router.get("/albums/{album_id}/videos")
def album_videos(album_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    return _list(db, user, album_id=album_id)


@router.get("/tracks/{track_id}/videos")
def track_videos(track_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    return _list(db, user, track_id=track_id)


@router.get("/videos/search")
def search_videos(
    q: str = Query(min_length=1, max_length=200),
    album_id: int | None = None,
    track_id: int | None = None,
    _: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """YouTube search results to pick from; `added` marks those already on this album/song."""
    try:
        results = youtube.search(q.strip())
    except youtube.YoutubeError as exc:
        raise api_error(503 if exc.code == "youtube_unreachable" else 400, exc.code) from None
    added: set[str] = set()
    if album_id or track_id:
        cond = Video.album_id == album_id if album_id else Video.track_id == track_id
        added = set(db.scalars(select(Video.youtube_id).where(cond)))
    return {"items": [{**r, "added": r["youtube_id"] in added} for r in results]}


class VideoIn(BaseModel):
    video: str = Field(min_length=11, max_length=500)  # the id from search, or a pasted link
    kind: Kind
    album_id: int | None = None
    track_id: int | None = None

    @model_validator(mode="after")
    def one_target(self):
        if (self.album_id is None) == (self.track_id is None):
            raise ValueError("album_id or track_id")
        return self


@router.post("/videos", status_code=201)
def add_video(body: VideoIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    youtube_id = youtube.video_id(body.video)
    if youtube_id is None:
        raise api_error(400, "video_bad_link")
    if body.album_id is not None and db.get(Album, body.album_id) is None:
        raise api_error(404, "not_found")
    if body.track_id is not None and db.get(Track, body.track_id) is None:
        raise api_error(404, "not_found")
    try:
        info = youtube.check(youtube_id)  # exists, may be embedded; its title and channel
    except youtube.YoutubeError as exc:
        raise api_error(503 if exc.code == "youtube_unreachable" else 400, exc.code) from None
    target = Video.album_id == body.album_id if body.album_id else Video.track_id == body.track_id
    position = db.scalar(select(func.coalesce(func.max(Video.position), -1)).where(target)) + 1
    video = Video(
        album_id=body.album_id, track_id=body.track_id, youtube_id=youtube_id, kind=body.kind,
        title=info["title"] or youtube_id, channel=info["channel"], position=position, added_by=user.id,
    )
    db.add(video)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise api_error(409, "video_exists") from None
    return video_out(video, user)


class VideoPatch(BaseModel):
    kind: Kind | None = None
    title: str | None = Field(None, min_length=1, max_length=500)
    position: int | None = Field(None, ge=0, le=10_000)


def _editable(db: Session, user: User, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise api_error(404, "not_found")
    if not (user.is_admin or video.added_by == user.id):
        raise api_error(403, "forbidden")
    return video


@router.patch("/videos/{video_id}")
def update_video(video_id: int, body: VideoPatch, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    video = _editable(db, user, video_id)
    if body.kind is not None:
        video.kind = body.kind
    if body.position is not None:
        video.position = body.position
    if body.title is not None:
        video.title = body.title.strip()
    db.commit()
    return video_out(video, user)


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    db.delete(_editable(db, user, video_id))
    db.commit()


# ---- video files on the NAS (library/video; the library is mounted read-only) ----
def _video_root() -> Path:
    return settings.video_dir


def _inside(rel: str) -> Path | None:
    """The file for a path relative to the video folder, only when it is really inside it."""
    root = _video_root().resolve()
    try:
        path = (root / rel).resolve()
    except (OSError, ValueError):
        return None
    if root not in path.parents or not path.is_file() or path.suffix.lower() not in VIDEO_EXTS:
        return None
    return path


@router.get("/videos/files")
def video_files(_: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """The video files in library/video (sub-folders too), each saying whether it is registered."""
    root = _video_root()
    if not root.is_dir():
        return {"folder": False, "items": []}
    registered = dict(db.execute(select(Video.file_path, Video.id).where(Video.file_path.is_not(None))).all())
    items = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "@", "#")))  # recycle bins, @eaDir
        for name in sorted(filenames):
            if name.startswith(".") or os.path.splitext(name)[1].lower() not in VIDEO_EXTS:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            items.append({"path": rel, "size": size, "video_id": registered.get(rel)})
        if len(items) >= 5000:
            break
    return {"folder": True, "items": items}


class VideoFileIn(BaseModel):
    path: str = Field(min_length=1, max_length=1000)  # relative to library/video
    kind: Kind
    title: str | None = Field(None, max_length=500)
    track_id: int | None = None  # optional: the song (or album) it belongs to
    album_id: int | None = None

    @model_validator(mode="after")
    def one_target_at_most(self):
        if self.track_id is not None and self.album_id is not None:
            raise ValueError("album_id or track_id")
        return self


@router.post("/videos/files", status_code=201)
def add_video_file(body: VideoFileIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    path = _inside(body.path)
    if path is None:
        raise api_error(404, "not_found")
    rel = os.path.relpath(path, _video_root().resolve())
    video = Video(
        file_path=rel, kind=body.kind, title=(body.title or "").strip() or Path(rel).stem,
        channel="", track_id=body.track_id, album_id=body.album_id, added_by=user.id,
    )
    db.add(video)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise api_error(409, "video_exists") from None
    return video_out(video, user)


@router.get("/videos/{video_id}/file")
def video_file(video_id: int, _: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """The file itself, for <video> (seeking uses Range requests)."""
    video = db.get(Video, video_id)
    path = _inside(video.file_path) if video is not None and video.file_path else None
    if path is None:
        raise api_error(404, "not_found")
    return FileResponse(path, media_type=VIDEO_TYPES.get(path.suffix.lower(), "application/octet-stream"))


# ---- video playlists (each person's own) ----
class VideoPlaylistIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class VideoIdsIn(BaseModel):
    video_ids: list[int] = Field(min_length=1, max_length=1000)


class EntryOrderIn(BaseModel):
    entry_ids: list[int]


def _own(db: Session, user: User, playlist_id: int) -> VideoPlaylist:
    playlist = db.get(VideoPlaylist, playlist_id)
    if playlist is None or playlist.user_id != user.id:
        raise api_error(404, "not_found")
    return playlist


def _playlist_out(p: VideoPlaylist, count: int, thumb: str | None = None) -> dict:
    return {"id": p.id, "name": p.name, "count": count, "thumb": thumb, "updated_at": p.updated_at}


@router.get("/video-playlists")
def video_playlists(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    rows = db.execute(
        select(VideoPlaylist, func.count(VideoPlaylistItem.id))
        .outerjoin(VideoPlaylistItem, VideoPlaylistItem.playlist_id == VideoPlaylist.id)
        .where(VideoPlaylist.user_id == user.id)
        .group_by(VideoPlaylist.id)
        .order_by(VideoPlaylist.updated_at.desc())
    ).all()
    # a picture for each: its first YouTube video's
    first = (
        select(VideoPlaylistItem.playlist_id, Video.youtube_id)
        .join(Video, Video.id == VideoPlaylistItem.video_id)
        .where(VideoPlaylistItem.playlist_id.in_([p.id for p, _ in rows]), Video.youtube_id.is_not(None))
        .order_by(VideoPlaylistItem.playlist_id, VideoPlaylistItem.position)
        .distinct(VideoPlaylistItem.playlist_id)
    )
    thumbs = dict(db.execute(first).all()) if rows else {}
    return {"items": [_playlist_out(p, n, thumbs.get(p.id)) for p, n in rows]}


@router.post("/video-playlists", status_code=201)
def create_video_playlist(body: VideoPlaylistIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = VideoPlaylist(user_id=user.id, name=body.name.strip())
    db.add(playlist)
    db.commit()
    return _playlist_out(playlist, 0)


@router.get("/video-playlists/{playlist_id}")
def video_playlist(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    playlist = _own(db, user, playlist_id)
    rows = db.execute(
        _listing(VideoPlaylistItem.id)
        .join(VideoPlaylistItem, VideoPlaylistItem.video_id == Video.id)
        .where(VideoPlaylistItem.playlist_id == playlist.id)
        .order_by(VideoPlaylistItem.position, VideoPlaylistItem.id)
    ).all()
    entries = [{"entry_id": r[-1], "video": list_item(r, user)} for r in rows]
    return {**_playlist_out(playlist, len(entries)), "entries": entries}


@router.patch("/video-playlists/{playlist_id}")
def rename_video_playlist(
    playlist_id: int, body: VideoPlaylistIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
):
    playlist = _own(db, user, playlist_id)
    playlist.name = body.name.strip()
    db.commit()
    count = db.scalar(select(func.count()).where(VideoPlaylistItem.playlist_id == playlist.id))
    return _playlist_out(playlist, count)


@router.delete("/video-playlists/{playlist_id}", status_code=204)
def delete_video_playlist(playlist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    db.delete(_own(db, user, playlist_id))
    db.commit()


@router.post("/video-playlists/{playlist_id}/videos", status_code=204)
def add_to_video_playlist(
    playlist_id: int, body: VideoIdsIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
):
    playlist = _own(db, user, playlist_id)
    valid = set(db.scalars(select(Video.id).where(Video.id.in_(body.video_ids))))
    position = db.scalar(
        select(func.coalesce(func.max(VideoPlaylistItem.position), -1)).where(VideoPlaylistItem.playlist_id == playlist.id)
    )
    for video_id in body.video_ids:
        if video_id in valid:
            position += 1
            db.add(VideoPlaylistItem(playlist_id=playlist.id, video_id=video_id, position=position))
    playlist.updated_at = func.now()
    db.commit()


@router.delete("/video-playlists/{playlist_id}/videos/{entry_id}", status_code=204)
def remove_from_video_playlist(
    playlist_id: int, entry_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
):
    playlist = _own(db, user, playlist_id)
    db.execute(delete(VideoPlaylistItem).where(VideoPlaylistItem.id == entry_id, VideoPlaylistItem.playlist_id == playlist.id))
    playlist.updated_at = func.now()
    db.commit()


@router.put("/video-playlists/{playlist_id}/order", status_code=204)
def reorder_video_playlist(
    playlist_id: int, body: EntryOrderIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
):
    playlist = _own(db, user, playlist_id)
    entries = {e.id: e for e in db.scalars(select(VideoPlaylistItem).where(VideoPlaylistItem.playlist_id == playlist.id))}
    if set(body.entry_ids) != set(entries) or len(body.entry_ids) != len(entries):
        raise api_error(400, "invalid_order")
    for position, entry_id in enumerate(body.entry_ids):
        entries[entry_id].position = position
    playlist.updated_at = func.now()
    db.commit()
