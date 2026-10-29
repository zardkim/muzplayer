import mimetypes
import os
import unicodedata

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..config import settings
from ..db import get_db
from ..models import Album, Artist, Favorite, Genre, Track, TrackGenre, User
from ..scanner import COVER_SIZES, cover_file
from ..security import api_error, current_user

router = APIRouter()

AUDIO_TYPES = {
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "ogg": "audio/ogg",
    "oga": "audio/ogg",
    "opus": "audio/ogg",
    "wav": "audio/wav",
    "wma": "audio/x-ms-wma",
    "ape": "audio/x-ape",
    "aif": "audio/aiff",
    "aiff": "audio/aiff",
}

AlbumArtist = aliased(Artist)


def like(q: str) -> str:
    q = unicodedata.normalize("NFC", q)  # stored text is NFC (see scanner)
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def track_query(user_id: int) -> Select:
    """Tracks joined with album/artist names and the user's favorite flag."""
    fav = exists().where(Favorite.user_id == user_id, Favorite.track_id == Track.id)
    return (
        select(Track, Album.title, Album.cover_path, fav.label("is_favorite"))
        .outerjoin(Album, Album.id == Track.album_id)
    )


def track_out(row) -> dict:
    track, album_title, cover_path, is_favorite = row
    return {
        "id": track.id,
        "title": track.title,
        "artist": track.artist_text,
        "artist_id": track.artist_id,
        "album": album_title or "",
        "album_id": track.album_id,
        "has_cover": bool(cover_path),
        "track_no": track.track_no,
        "disc_no": track.disc_no,
        "duration": track.duration,
        "format": track.format,
        "is_favorite": bool(is_favorite),
        "missing": track.missing_at is not None,
    }


def present_tracks():
    return Track.missing_at.is_(None)


@router.get("/tracks")
def list_tracks(
    q: str = "",
    genre_id: int | None = None,
    album_id: int | None = None,
    artist_id: int | None = None,
    sort: str = Query("title", pattern="^(title|artist|album|recent)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    conds = [present_tracks()]
    if q.strip():
        pattern = like(q.strip())
        conds.append(or_(Track.title.ilike(pattern), Track.artist_text.ilike(pattern), Album.title.ilike(pattern)))
    if genre_id:
        conds.append(exists().where(TrackGenre.track_id == Track.id, TrackGenre.genre_id == genre_id))
    if album_id:
        conds.append(Track.album_id == album_id)
    if artist_id:
        conds.append(Track.artist_id == artist_id)

    order = {
        "title": [func.lower(Track.title)],
        "artist": [func.lower(Track.artist_text), Album.title, Track.disc_no, Track.track_no],
        "album": [Album.title, Track.disc_no, Track.track_no],
        "recent": [Track.created_at.desc(), Track.id.desc()],
    }[sort]

    total = db.scalar(
        select(func.count()).select_from(Track).outerjoin(Album, Album.id == Track.album_id).where(*conds)
    )
    rows = db.execute(track_query(user.id).where(*conds).order_by(*order, Track.id).limit(limit).offset(offset))
    return {"items": [track_out(r) for r in rows], "total": total}


def album_list_query(conds) -> Select:
    count = func.count(Track.id)
    return (
        select(Album, AlbumArtist.name, count.label("track_count"))
        .join(Track, and_(Track.album_id == Album.id, present_tracks()))
        .outerjoin(AlbumArtist, AlbumArtist.id == Album.album_artist_id)
        .where(*conds)
        .group_by(Album.id, AlbumArtist.name)
    )


def album_out(row) -> dict:
    album, artist_name, track_count = row
    return {
        "id": album.id,
        "title": album.title,
        "artist": artist_name or "",
        "artist_id": album.album_artist_id,
        "year": album.year,
        "has_cover": bool(album.cover_path),
        "track_count": track_count,
    }


@router.get("/albums")
def list_albums(
    q: str = "",
    artist_id: int | None = None,
    sort: str = Query("recent", pattern="^(recent|title|artist|year)$"),
    limit: int = Query(60, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    conds = []
    if q.strip():
        pattern = like(q.strip())
        conds.append(or_(Album.title.ilike(pattern), AlbumArtist.name.ilike(pattern)))
    if artist_id:
        conds.append(Album.album_artist_id == artist_id)
    order = {
        "recent": [Album.created_at.desc()],
        "title": [func.lower(Album.title)],
        "artist": [func.lower(AlbumArtist.name), Album.year],
        "year": [Album.year.desc().nulls_last()],
    }[sort]
    base = album_list_query(conds)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(base.order_by(*order, Album.id).limit(limit).offset(offset))
    return {"items": [album_out(r) for r in rows], "total": total}


@router.get("/albums/{album_id}")
def get_album(album_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.execute(album_list_query([Album.id == album_id])).first()
    if row is None:
        raise api_error(404, "not_found")
    tracks = db.execute(
        track_query(user.id)
        .where(Track.album_id == album_id, present_tracks())
        .order_by(Track.disc_no.nulls_first(), Track.track_no.nulls_last(), Track.title)
    )
    return {**album_out(row), "tracks": [track_out(t) for t in tracks]}


@router.get("/albums/{album_id}/cover")
def get_cover(
    album_id: int,
    size: str = Query("thumb", pattern="^(thumb|large)$"),
    _: User = Depends(current_user),
):
    path = cover_file(album_id, size)
    if size not in COVER_SIZES or not path.exists():
        raise api_error(404, "not_found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/artists")
def list_artists(
    q: str = "",
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    album_count = (
        select(func.count(func.distinct(Album.id)))
        .join(Track, and_(Track.album_id == Album.id, present_tracks()))
        .where(Album.album_artist_id == Artist.id)
        .scalar_subquery()
    )
    track_count = (
        select(func.count(Track.id)).where(Track.artist_id == Artist.id, present_tracks()).scalar_subquery()
    )
    conds = [or_(album_count > 0, track_count > 0)]
    if q.strip():
        conds.append(Artist.name.ilike(like(q.strip())))
    base = select(Artist, album_count.label("albums"), track_count.label("tracks")).where(*conds)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(base.order_by(Artist.sort_name, Artist.id).limit(limit).offset(offset))
    return {
        "items": [
            {"id": a.id, "name": a.name, "album_count": albums, "track_count": tracks}
            for a, albums, tracks in rows
        ],
        "total": total,
    }


@router.get("/artists/{artist_id}")
def get_artist(artist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise api_error(404, "not_found")
    albums = db.execute(
        album_list_query([Album.album_artist_id == artist_id]).order_by(Album.year.desc().nulls_last())
    )
    tracks = db.execute(
        track_query(user.id)
        .where(Track.artist_id == artist_id, present_tracks())
        .order_by(func.lower(Track.title))
        .limit(500)
    )
    return {
        "id": artist.id,
        "name": artist.name,
        "albums": [album_out(a) for a in albums],
        "tracks": [track_out(t) for t in tracks],
    }


@router.get("/genres")
def list_genres(_: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Genre.id, Genre.name, func.count(Track.id))
        .join(TrackGenre, TrackGenre.genre_id == Genre.id)
        .join(Track, and_(Track.id == TrackGenre.track_id, present_tracks()))
        .group_by(Genre.id)
        .order_by(func.lower(Genre.name))
    )
    return {"items": [{"id": i, "name": n, "track_count": c} for i, n, c in rows]}


@router.get("/tracks/{track_id}/stream")
def stream(track_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    track = db.get(Track, track_id)
    if track is None or track.missing_at is not None:
        raise api_error(404, "not_found")
    # file_path comes from the scanner and may go through symlinked folders, so check the
    # path as written (no "..") rather than where it finally resolves
    rel = os.path.normpath(track.file_path)
    if os.path.isabs(rel) or rel.startswith(".."):
        raise api_error(404, "not_found")
    path = os.path.join(settings.music_dir, rel)
    if not os.path.isfile(path):
        raise api_error(404, "not_found")
    media_type = AUDIO_TYPES.get(track.format) or mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})
