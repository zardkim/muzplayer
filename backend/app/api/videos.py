"""Music videos: YouTube videos of albums and songs, and video files on the NAS (library/video).
Anyone may add one; the person who added it or an admin may change or remove it."""

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from .. import youtube
from ..config import settings
from ..db import get_db
from ..models import Album, Artist, Track, User, Video
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


@router.get("/videos")
def all_videos(
    kind: Literal["mv", "live", "cover", "other"] | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """Every video added (the Music videos page), YouTube and NAS files, newest first, each with its
    song or album (a NAS file may have none)."""
    album_of_track = aliased(Album)
    cond = [Video.kind == kind] if kind else []
    total = db.scalar(select(func.count(Video.id)).where(*cond))
    rows = db.execute(
        select(
            Video, Track.title, Track.artist_text, Track.album_id, album_of_track.cover_path, album_of_track.cover_version,
            Album.title, Artist.name, Album.cover_path, Album.cover_version,
        )
        .outerjoin(Track, Track.id == Video.track_id)
        .outerjoin(album_of_track, album_of_track.id == Track.album_id)
        .outerjoin(Album, Album.id == Video.album_id)
        .outerjoin(Artist, Artist.id == Album.album_artist_id)
        .where(*cond)
        .order_by(Video.created_at.desc(), Video.id.desc())
        .offset(offset)
        .limit(limit)
    )
    items = []
    for v, t_title, t_artist, t_album, t_cover, t_cover_v, a_title, a_artist, a_cover, a_cover_v in rows:
        if v.track_id is None and v.album_id is None:
            target = None
        elif v.track_id is not None:
            target = {"type": "track", "title": t_title, "artist": t_artist or "", "album_id": t_album,
                      "has_cover": bool(t_cover), "cover_v": t_cover_v if t_cover else 0}
        else:
            target = {"type": "album", "title": a_title, "artist": a_artist or "", "album_id": v.album_id,
                      "has_cover": bool(a_cover), "cover_v": a_cover_v if a_cover else 0}
        items.append({**video_out(v, user), "target": target})
    return {"items": items, "total": total}


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
