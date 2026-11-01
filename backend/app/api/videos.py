"""Music videos: YouTube videos of albums and songs, and video files on the NAS (library/video).
Admins add, change and remove them; everyone watches them, likes them and puts them in their own
video playlists."""

import os
import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import case, delete, exists, func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from .. import search_index, video_thumbs, youtube
from ..config import settings
from ..db import get_db
from ..models import Album, Artist, Track, TrackGenre, User, Video, VideoFavorite, VideoPlaylist, VideoPlaylistItem
from ..security import admin_user, api_error, current_user

router = APIRouter()

KINDS = ("mv", "concert", "tv", "fan", "other")
Kind = Literal["mv", "concert", "tv", "fan", "other"]
# a name or title: spaces around it dropped, then something must be left
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
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
        "duration": v.duration,
        "kind": v.kind,
        "title": v.title,
        "channel": v.channel,
        "album_id": v.album_id,
        "track_id": v.track_id,
        "can_edit": user.is_admin,
        "created_at": v.created_at,
    }


def _list(db: Session, user: User, **target) -> dict:
    (column, value), = target.items()
    rows = db.scalars(
        select(Video).where(getattr(Video, column) == value).order_by(Video.position, Video.id)
    )
    return {"items": [video_out(v, user) for v in rows]}


_album_of_track = aliased(Album)


def _liked(user_id: int):
    return exists().where(VideoFavorite.user_id == user_id, VideoFavorite.video_id == Video.id).correlate(Video)


def _listing(user_id: int, *extra):
    """Videos with their song or album and whether this person liked them, for lists (Music videos
    page, search, video playlists); extra columns come last."""
    return (
        select(
            Video, Track.title, Track.artist_text, Track.album_id, _album_of_track.cover_path,
            _album_of_track.cover_version, Album.title, Artist.name, Album.cover_path, Album.cover_version,
            _liked(user_id), *extra,
        )
        .outerjoin(Track, Track.id == Video.track_id)
        .outerjoin(_album_of_track, _album_of_track.id == Track.album_id)
        .outerjoin(Album, Album.id == Video.album_id)
        .outerjoin(Artist, Artist.id == Album.album_artist_id)
    )


def list_item(row, user: User) -> dict:
    v, t_title, t_artist, t_album, t_cover, t_cover_v, a_title, a_artist, a_cover, a_cover_v, liked = row[:11]
    if v.track_id is None and v.album_id is None:
        target = None
    elif v.track_id is not None:
        target = {"type": "track", "title": t_title, "artist": t_artist or "", "album_id": t_album,
                  "has_cover": bool(t_cover), "cover_v": t_cover_v if t_cover else 0}
    else:
        target = {"type": "album", "title": a_title, "artist": a_artist or "", "album_id": v.album_id,
                  "has_cover": bool(a_cover), "cover_v": a_cover_v if a_cover else 0}
    return {**video_out(v, user), "target": target, "is_favorite": bool(liked)}


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
    liked: bool = False,  # only the videos this person liked
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
    if liked:
        cond.append(_liked(user.id))
    total = db.scalar(select(func.count()).select_from(_listing(user.id).where(*cond).subquery()))
    rows = db.execute(_listing(user.id).where(*cond).order_by(Video.created_at.desc(), Video.id.desc()).offset(offset).limit(limit))
    return {"items": [list_item(r, user) for r in rows], "total": total}


# ---- what is like a video (the video player, under it) ----
_TrackOfVideo = aliased(Track)
_AlbumOfVideo = aliased(Album)


def _seed(db: Session, video: Video) -> tuple[int | None, list[int]]:
    """(artist id, genre ids) of the song or album a video belongs to."""
    if video.track_id is not None:
        track = db.get(Track, video.track_id)
        artist_id = track.artist_id if track else None
        genres = list(db.scalars(select(TrackGenre.genre_id).where(TrackGenre.track_id == video.track_id)))
    elif video.album_id is not None:
        album = db.get(Album, video.album_id)
        artist_id = album.album_artist_id if album else None
        genres = list(db.scalars(
            select(TrackGenre.genre_id).join(Track, Track.id == TrackGenre.track_id).where(Track.album_id == video.album_id).distinct()
        ))
    else:
        return None, []
    return artist_id, genres


@router.get("/videos/{video_id}/related")
def related(video_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """Similar music videos (the same artist, a shared genre, the same kind; a little chance mixes
    them) and similar artists (the library's artists most often in this one's genres)."""
    from .library import image_v, present_tracks

    video = db.get(Video, video_id)
    if video is None:
        raise api_error(404, "not_found")
    artist_id, genres = _seed(db, video)

    # each video's artist: its song's, or its album's
    v_artist = func.coalesce(_TrackOfVideo.artist_id, _AlbumOfVideo.album_artist_id)
    v_track_genre = exists().where(TrackGenre.track_id == Video.track_id, TrackGenre.genre_id.in_(genres or [-1]))
    v_album_genre = exists().where(
        Track.album_id == Video.album_id, TrackGenre.track_id == Track.id, TrackGenre.genre_id.in_(genres or [-1])
    )
    score = (
        (case((v_artist == artist_id, 4), else_=0) if artist_id is not None else literal(0))
        + case((or_(v_track_genre, v_album_genre), 3), else_=0)
        + case((Video.kind == video.kind, 1), else_=0)
        + func.random() * 2
    )
    ids = list(db.scalars(
        select(Video.id)
        .outerjoin(_TrackOfVideo, _TrackOfVideo.id == Video.track_id)
        .outerjoin(_AlbumOfVideo, _AlbumOfVideo.id == Video.album_id)
        .where(Video.id != video.id)
        .order_by(score.desc())
        .limit(12)
    ))
    rows = {r[0].id: r for r in db.execute(_listing(user.id).where(Video.id.in_(ids)))} if ids else {}
    videos = [list_item(rows[i], user) for i in ids if i in rows]

    artists = []
    if genres:
        shared = func.count(func.distinct(TrackGenre.genre_id))
        found = db.execute(
            select(Artist, shared.label("n"))
            .join(Track, Track.artist_id == Artist.id)
            .join(TrackGenre, TrackGenre.track_id == Track.id)
            .where(TrackGenre.genre_id.in_(genres), present_tracks(), Track.chart_id.is_(None),
                   *( [Artist.id != artist_id] if artist_id is not None else []))
            .group_by(Artist.id)
            .order_by(shared.desc(), func.count(Track.id).desc())
            .limit(10)
        ).all()
        artists = [{"id": a.id, "name": a.name, "image_v": image_v(a)} for a, _ in found]
    # untagged genres (or few artists in them): the artists of the similar videos fill in
    if len(artists) < 10 and ids:
        have = {a["id"] for a in artists} | ({artist_id} if artist_id is not None else set())
        by_video = dict(db.execute(
            select(Video.id, v_artist)
            .outerjoin(_TrackOfVideo, _TrackOfVideo.id == Video.track_id)
            .outerjoin(_AlbumOfVideo, _AlbumOfVideo.id == Video.album_id)
            .where(Video.id.in_(ids))
        ).all())
        more = [by_video.get(i) for i in ids]
        more = list(dict.fromkeys(a for a in more if a is not None and a not in have))[: 10 - len(artists)]
        if more:
            found = {a.id: a for a in db.scalars(select(Artist).where(Artist.id.in_(more)))}
            artists += [{"id": a.id, "name": a.name, "image_v": image_v(found[a.id])} for a in (found[i] for i in more if i in found)]
    return {"videos": videos, "artists": artists}


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
    _: User = Depends(admin_user),
    db: Session = Depends(get_db, scope="function"),
):
    """YouTube search results to pick from (adding videos is an admin's); `added` marks those already on this album/song."""
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
def add_video(body: VideoIn, user: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
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
    title: Title | None = None
    position: int | None = Field(None, ge=0, le=10_000)


def _editable(db: Session, user: User, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise api_error(404, "not_found")
    if not user.is_admin:
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
    video_thumbs.remove(video_id)


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


# ---- a NAS file's song, found from its name ----
# [MV], (Official Video), 【4K】, (직캠)...: not part of the song's title
_NOISE_IN_BRACKETS = re.compile(
    r"[\[(【（][^\])】）]*?(?:m/?v|official|video|lyric|live|4k|8k|1080p|720p|hd|uhd|audio|teaser|가사|뮤비|뮤직\s*비디오|직캠|공식|"
    r"stage|performance|교차|무대|special|clip|remaster)[^\])】）]*[\])】）]",
    re.I,
)
_NOISE_WORDS = re.compile(r"\b(?:official\s+(?:music\s+)?video|music\s+video|m/?v|4k|8k|1080p|720p|2160p|hd|uhd|remastered)\b", re.I)
_BRACKETS = re.compile(r"[\[(【（][^\])】）]*[\])】）]")


def _clean(text: str) -> str:
    return search_index.norm(_NOISE_WORDS.sub(" ", _NOISE_IN_BRACKETS.sub(" ", text)))


def _bare(title: str) -> str:
    """A song's title without its brackets: "밤편지 (Live)" -> "밤편지"."""
    return search_index.norm(_BRACKETS.sub(" ", title))


def guess_track(db: Session, rel: str, title: str | None = None) -> int | None:
    """The song a NAS video is of, when its name says so without doubt: "Artist - Title" (either way
    round), the title alone, or the title in a folder named after the artist. None when no song or
    songs of different artists fit."""
    path = Path(rel)
    folder = path.parent.name if path.parent != Path(".") else ""
    guesses: list[tuple[str, str]] = []  # (artist or "", title), the likeliest first
    for text in dict.fromkeys(t for t in (title, path.stem) if t):
        text = text.replace("_", " ")
        if " - " in text:
            a, b = (s.strip() for s in text.split(" - ", 1))
            guesses += [(a, b), (b, a)]
        if folder:
            guesses.append((folder, text))
        guesses.append(("", text))
        if " - " in text:
            guesses.append(("", b))  # the artist written another way ("IU" for "아이유"): the title alone
    for artist, song in guesses:
        wants = {w for w in (_clean(song), _bare(song)) if w}  # as written; without anything in brackets
        if not wants:
            continue
        words = min(wants, key=len).split()
        pattern = "%" + "%".join(w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for w in words) + "%"
        rows = db.execute(
            select(Track.id, Track.title, Track.artist_text, Album.kind)
            .outerjoin(Album, Album.id == Track.album_id)
            .where(Track.missing_at.is_(None), Track.canonical_track_id.is_(None), Track.title.ilike(pattern))
            .limit(200)
        ).all()
        hits = [r for r in rows if wants & {search_index.norm(r.title), _bare(r.title)}]
        if artist:
            who = _clean(artist)
            hits = [r for r in hits if who and (who in search_index.norm(r.artist_text) or search_index.norm(r.artist_text) in who)]
        if not hits:
            continue
        if len({search_index.norm(r.artist_text) for r in hits}) > 1:
            return None  # the same title by different artists: don't guess
        # one song (perhaps on several albums): its album copy before a chart's
        hits.sort(key=lambda r: (r.kind == "chart", r.id))
        return hits[0].id
    return None


@router.get("/videos/files")
def video_files(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """The video files in library/video (sub-folders too), each saying whether it is registered.
    Registering the NAS's files is an admin's job (everyone watches them)."""
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
def add_video_file(body: VideoFileIn, user: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    path = _inside(body.path)
    if path is None:
        raise api_error(404, "not_found")
    rel = os.path.relpath(path, _video_root().resolve())
    title = (body.title or "").strip() or Path(rel).stem
    track_id = body.track_id
    if track_id is None and body.album_id is None:
        track_id = guess_track(db, rel, title)  # its song, when the name says so
    video = Video(
        file_path=rel, kind=body.kind, title=title,
        channel="", track_id=track_id, album_id=body.album_id, added_by=user.id,
    )
    db.add(video)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise api_error(409, "video_exists") from None
    video_thumbs.make_later(video.id, path)
    return list_item(db.execute(_listing(user.id).where(Video.id == video.id)).one(), user)


class LinkIn(BaseModel):
    track_id: int | None = None  # the song picked (Music videos page: searched for by a keyword)
    auto: bool = False  # find its song from its name instead; neither: no song


@router.post("/videos/{video_id}/link")
def link_video(video_id: int, body: LinkIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """A NAS file's song: the one picked, found again from its name (404 video_no_song when none
    fits), or none."""
    video = _editable(db, user, video_id)
    if not video.file_path:
        raise api_error(400, "not_a_file")
    if body.track_id is not None:
        if db.get(Track, body.track_id) is None:
            raise api_error(404, "not_found")
        track_id = body.track_id
    else:
        track_id = guess_track(db, video.file_path, video.title) if body.auto else None
        if body.auto and track_id is None:
            raise api_error(404, "video_no_song")
    video.track_id, video.album_id = track_id, None
    db.commit()
    return list_item(db.execute(_listing(user.id).where(Video.id == video.id)).one(), user)




@router.put("/videos/{video_id}/favorite", status_code=204)
def like_video(video_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    if db.get(Video, video_id) is None:
        raise api_error(404, "not_found")
    if db.get(VideoFavorite, (user.id, video_id)) is None:
        db.add(VideoFavorite(user_id=user.id, video_id=video_id))
        db.commit()


@router.delete("/videos/{video_id}/favorite", status_code=204)
def unlike_video(video_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    db.execute(delete(VideoFavorite).where(VideoFavorite.user_id == user.id, VideoFavorite.video_id == video_id))
    db.commit()


@router.get("/videos/{video_id}/thumb")
def video_thumb(video_id: int, _: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """A NAS file's thumbnail (video_thumbs.py), made the first time when it isn't there yet."""
    video = db.get(Video, video_id)
    path = _inside(video.file_path) if video is not None and video.file_path else None
    if path is None:
        raise api_error(404, "not_found")
    db.close()  # making one can take a few seconds: don't hold a connection meanwhile
    thumb = video_thumbs.ensure(video_id, path)
    if thumb is None:
        raise api_error(404, "not_found")
    return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/videos/{video_id}/thumb", status_code=204)
def remake_video_thumb(video_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """A NAS file's thumbnail made again from another scene (who added it, or an admin)."""
    video = _editable(db, user, video_id)
    path = _inside(video.file_path) if video.file_path else None
    if path is None:
        raise api_error(404, "not_found")
    db.close()
    if not video_thumbs.remake(video_id, path):
        raise api_error(503, "thumb_failed")


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
    name: Name


class VideoIdsIn(BaseModel):
    video_ids: list[int] = Field(min_length=1, max_length=1000)


class EntryOrderIn(BaseModel):
    entry_ids: list[int]


def _own(db: Session, user: User, playlist_id: int) -> VideoPlaylist:
    playlist = db.get(VideoPlaylist, playlist_id)
    if playlist is None or playlist.user_id != user.id:
        raise api_error(404, "not_found")
    return playlist


DEFAULT_VIDEO_NAMES = {"ko": "기본 영상 플레이리스트", "en": "My video playlist"}


def _playlist_out(p: VideoPlaylist, count: int, thumb: str | None = None) -> dict:
    return {"id": p.id, "name": p.name, "count": count, "thumb": thumb, "is_default": p.is_default, "updated_at": p.updated_at}


@router.get("/video-playlists")
def video_playlists(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    from .me import ensure_default

    ensure_default(db, VideoPlaylist, user, DEFAULT_VIDEO_NAMES)
    rows = db.execute(
        select(VideoPlaylist, func.count(VideoPlaylistItem.id))
        .outerjoin(VideoPlaylistItem, VideoPlaylistItem.playlist_id == VideoPlaylist.id)
        .where(VideoPlaylist.user_id == user.id)
        .group_by(VideoPlaylist.id)
        .order_by(VideoPlaylist.is_default.desc(), VideoPlaylist.updated_at.desc())
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
        _listing(user.id, VideoPlaylistItem.id)
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
    playlist = _own(db, user, playlist_id)
    if playlist.is_default:
        raise api_error(400, "default_playlist")  # everyone keeps theirs
    db.delete(playlist)
    db.commit()


@router.post("/video-playlists/{playlist_id}/videos")
def add_to_video_playlist(
    playlist_id: int, body: VideoIdsIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
):
    playlist = _own(db, user, playlist_id)
    """Adds the videos not in the list yet: {"added": n, "skipped": videos already there}."""
    valid = set(db.scalars(select(Video.id).where(Video.id.in_(body.video_ids))))
    there = set(db.scalars(select(VideoPlaylistItem.video_id).where(VideoPlaylistItem.playlist_id == playlist.id)))
    position = db.scalar(
        select(func.coalesce(func.max(VideoPlaylistItem.position), -1)).where(VideoPlaylistItem.playlist_id == playlist.id)
    )
    added = skipped = 0
    for video_id in body.video_ids:
        if video_id not in valid:
            continue
        if video_id in there:
            skipped += 1
            continue
        there.add(video_id)
        position += 1
        added += 1
        db.add(VideoPlaylistItem(playlist_id=playlist.id, video_id=video_id, position=position))
    playlist.updated_at = func.now()
    db.commit()
    return {"added": added, "skipped": skipped}


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
