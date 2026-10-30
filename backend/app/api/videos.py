"""YouTube videos of albums and songs (music videos, live, covers by others). Anyone may add one;
the person who added it or an admin may change or remove it."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import youtube
from ..db import get_db
from ..models import Album, Track, User, Video
from ..security import api_error, current_user

router = APIRouter()

KINDS = ("mv", "live", "cover", "other")


def video_out(v: Video, user: User) -> dict:
    return {
        "id": v.id,
        "youtube_id": v.youtube_id,
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


@router.get("/albums/{album_id}/videos")
def album_videos(album_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _list(db, user, album_id=album_id)


@router.get("/tracks/{track_id}/videos")
def track_videos(track_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _list(db, user, track_id=track_id)


@router.get("/videos/search")
def search_videos(
    q: str = Query(min_length=1, max_length=200),
    album_id: int | None = None,
    track_id: int | None = None,
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
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
    kind: Literal["mv", "live", "cover", "other"]
    album_id: int | None = None
    track_id: int | None = None

    @model_validator(mode="after")
    def one_target(self):
        if (self.album_id is None) == (self.track_id is None):
            raise ValueError("album_id or track_id")
        return self


@router.post("/videos", status_code=201)
def add_video(body: VideoIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
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
    kind: Literal["mv", "live", "cover", "other"] | None = None
    position: int | None = Field(None, ge=0, le=10_000)


def _editable(db: Session, user: User, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise api_error(404, "not_found")
    if not (user.is_admin or video.added_by == user.id):
        raise api_error(403, "forbidden")
    return video


@router.patch("/videos/{video_id}")
def update_video(video_id: int, body: VideoPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    video = _editable(db, user, video_id)
    if body.kind is not None:
        video.kind = body.kind
    if body.position is not None:
        video.position = body.position
    db.commit()
    return video_out(video, user)


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_editable(db, user, video_id))
    db.commit()
