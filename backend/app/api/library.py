import mimetypes
import os
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from .. import artist_images
from ..cache import cached, image_response, library_version, shared_json
from ..config import settings
from ..db import get_db
from ..lyrics import read_lyrics
from ..models import Album, AlbumFavorite, AlbumRating, Artist, Favorite, Genre, Track, TrackGenre, TrackRating, User, Video
from ..scanner import COVER_SIZES, cover_file, search_key
from ..security import api_error, current_user

router = APIRouter()

AUDIO_TYPES = {
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
    "m4b": "audio/mp4",
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
    # correlate only to Track: the favorites list joins Favorite itself, which would otherwise
    # be swallowed by auto-correlation and leave the subquery without a FROM
    fav = exists().where(Favorite.user_id == user_id, Favorite.track_id == Track.id).correlate(Track)
    rating = (
        select(TrackRating.rating)
        .where(TrackRating.user_id == user_id, TrackRating.track_id == Track.id)
        .correlate(Track)
        .scalar_subquery()
    )
    video = exists().where(Video.track_id == Track.id).correlate(Track)
    return (
        select(
            Track, Album.title, Album.cover_path, Album.kind, fav.label("is_favorite"), Album.cover_version,
            rating.label("rating"), video.label("has_video"),
        )
        .outerjoin(Album, Album.id == Track.album_id)
    )


def track_out(row) -> dict:
    track, album_title, cover_path, album_kind, is_favorite, cover_version, rating, has_video = row
    return {
        "id": track.id,
        "title": track.title,
        "artist": track.artist_text,
        "artist_id": track.artist_id,
        "album": album_title or "",
        "album_id": track.album_id,
        "album_kind": album_kind or "album",
        "has_cover": bool(cover_path),
        "cover_v": cover_version if cover_path else 0,
        "track_no": track.track_no,
        "disc_no": track.disc_no,
        "duration": track.duration,
        "format": track.format,
        "is_favorite": bool(is_favorite),
        "rating": rating,  # this user's stars, None when not rated
        "has_video": bool(has_video),
        "missing": track.missing_at is not None,
    }


def present_tracks():
    return Track.missing_at.is_(None)


def listed_tracks():
    """Present tracks minus duplicate copies (an older chart week of the same song)."""
    return and_(Track.missing_at.is_(None), Track.canonical_track_id.is_(None))


def not_chart():
    return Album.kind != "chart"


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
    conds = [listed_tracks()]
    if q.strip():
        # one column with a trigram index instead of three ILIKEs (title, artist, album)
        conds.append(Track.search_text.like(like(search_key(q.strip()))))
    if genre_id:
        conds.append(exists().where(TrackGenre.track_id == Track.id, TrackGenre.genre_id == genre_id))
    if album_id:
        conds.append(Track.album_id == album_id)
    if artist_id:
        conds.append(Track.artist_id == artist_id)
        conds.append(Track.chart_id.is_(None))

    order = {
        "title": [func.lower(Track.title)],
        "artist": [func.lower(Track.artist_text), Album.title, Track.disc_no, Track.track_no],
        "album": [Album.title, Track.disc_no, Track.track_no],
        "recent": [Track.created_at.desc(), Track.id.desc()],
    }[sort]

    # the rows carry this user's favorites; only the count is the same for everyone
    _, total = cached(
        db,
        f"tracks-total:{q.strip()}:{genre_id}:{album_id}:{artist_id}",
        lambda: db.scalar(select(func.count()).select_from(Track).where(*conds)),
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
        "kind": album.kind,
        "year": album.year,
        "has_cover": bool(album.cover_path),
        "cover_v": album.cover_version if album.cover_path else 0,
        "track_count": track_count,
    }


@router.get("/albums")
def list_albums(
    request: Request,
    q: str = "",
    artist_id: int | None = None,
    kind: str | None = Query(None, pattern="^(album|unofficial|compilation)$"),
    sort: str = Query("recent", pattern="^(recent|title|artist|year|rating)$"),
    limit: int = Query(60, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    conds = [not_chart()]
    if kind:
        conds.append(Album.kind == kind)
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
        "rating": [AlbumRating.rating.desc()],
    }[sort]

    if sort == "rating":  # my rated albums, best first: per user, so never from the shared cache
        base = album_list_query(conds).join(
            AlbumRating, and_(AlbumRating.album_id == Album.id, AlbumRating.user_id == user.id)
        ).group_by(AlbumRating.rating)
        total = db.scalar(select(func.count()).select_from(base.subquery()))
        rows = db.execute(base.order_by(*order, Album.id).limit(limit).offset(offset))
        return {"items": [album_out(r) for r in rows], "total": total}

    def build():
        base = album_list_query(conds)
        total = db.scalar(select(func.count()).select_from(base.subquery()))
        rows = db.execute(base.order_by(*order, Album.id).limit(limit).offset(offset))
        return {"items": [album_out(r) for r in rows], "total": total}

    return shared_json(request, db, f"albums:{q.strip()}:{artist_id}:{kind}:{sort}:{limit}:{offset}", build)


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
    tracks = [track_out(t) for t in tracks]
    rated = [t["rating"] for t in tracks if t["rating"]]
    return {
        **album_out(row),
        # this user's marks: the album's own stars, and the average of its songs' as a hint
        "rating": db.scalar(select(AlbumRating.rating).where(AlbumRating.user_id == user.id, AlbumRating.album_id == album_id)),
        "track_rating_avg": round(sum(rated) / len(rated), 1) if rated else None,
        "is_favorite": db.get(AlbumFavorite, (user.id, album_id)) is not None,
        "video_count": db.scalar(select(func.count()).where(Video.album_id == album_id)),
        "tracks": tracks,
    }


@router.get("/albums/{album_id}/cover")
def get_cover(
    request: Request,
    album_id: int,
    size: str = Query("thumb", pattern="^(thumb|large)$"),
    v: int | None = None,
    _: User = Depends(current_user),
):
    """v (the album's cover_v) only makes the URL change with the cover; it is not checked."""
    path = cover_file(album_id, size)
    if size not in COVER_SIZES or not path.exists():
        raise api_error(404, "not_found")
    return image_response(request, path, versioned=v is not None)


@router.get("/artists")
def list_artists(
    request: Request,
    q: str = "",
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    def build():
        # counted once for all artists (grouped), not once per artist
        albums = (
            select(Album.album_artist_id.label("artist_id"), func.count(func.distinct(Album.id)).label("n"))
            .join(Track, and_(Track.album_id == Album.id, present_tracks()))
            .where(not_chart(), Album.album_artist_id.is_not(None))
            .group_by(Album.album_artist_id)
            .subquery()
        )
        tracks = (
            select(Track.artist_id.label("artist_id"), func.count().label("n"))
            .where(present_tracks(), Track.chart_id.is_(None), Track.artist_id.is_not(None))
            .group_by(Track.artist_id)
            .subquery()
        )
        album_count = func.coalesce(albums.c.n, 0)
        track_count = func.coalesce(tracks.c.n, 0)
        conds = [or_(album_count > 0, track_count > 0)]
        if q.strip():
            conds.append(Artist.name.ilike(like(q.strip())))
        base = (
            select(Artist, album_count.label("albums"), track_count.label("tracks"))
            .outerjoin(albums, albums.c.artist_id == Artist.id)
            .outerjoin(tracks, tracks.c.artist_id == Artist.id)
            .where(*conds)
        )
        total = db.scalar(select(func.count()).select_from(base.subquery()))
        rows = db.execute(base.order_by(Artist.sort_name, Artist.id).limit(limit).offset(offset))
        return {
            "items": [
                {"id": a.id, "name": a.name, "album_count": n_albums, "track_count": n_tracks, "image_v": image_v(a)}
                for a, n_albums, n_tracks in rows
            ],
            "total": total,
        }

    return shared_json(request, db, f"artists:{q.strip()}:{limit}:{offset}", build)


def image_v(artist: Artist) -> int:
    """The photo's version for its URL; 0 = no photo."""
    return (artist.image_version or 1) if artist_images.has_image(artist) else 0


def image_credit(artist: Artist) -> dict | None:
    """Where a Wikipedia photo came from (shown under it, as its licence asks)."""
    source = artist.image_path or ""
    if not source.startswith("wiki:"):
        return None
    _, wiki, title = source.split(":", 2)
    return {"wiki": wiki, "title": title, "url": f"https://{wiki}.wikipedia.org/wiki/{title.replace(' ', '_')}"}


@router.get("/artists/{artist_id}/image")
def get_artist_image(
    request: Request,
    artist_id: int,
    size: str = Query("thumb", pattern="^(thumb|large)$"),
    v: int | None = None,
    _: User = Depends(current_user),
):
    path = artist_images.image_file(artist_id, size)
    if not path.exists():
        raise api_error(404, "not_found")
    return image_response(request, path, versioned=v is not None)


@router.get("/artists/{artist_id}")
def get_artist(artist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise api_error(404, "not_found")
    albums = db.execute(
        album_list_query([Album.album_artist_id == artist_id, not_chart()]).order_by(Album.year.desc().nulls_last())
    )
    tracks = db.execute(
        track_query(user.id)
        .where(Track.artist_id == artist_id, present_tracks(), Track.chart_id.is_(None))
        .order_by(func.lower(Track.title))
        .limit(500)
    )
    return {
        "id": artist.id,
        "name": artist.name,
        "image_v": image_v(artist),
        "image_credit": image_credit(artist),
        "image_removed": artist.image_path == "none",
        "albums": [album_out(a) for a in albums],
        "tracks": [track_out(t) for t in tracks],
    }


@router.get("/genres")
def list_genres(request: Request, _: User = Depends(current_user), db: Session = Depends(get_db)):
    def build():
        rows = db.execute(
            select(Genre.id, Genre.name, func.count(Track.id))
            .join(TrackGenre, TrackGenre.genre_id == Genre.id)
            .join(Track, and_(Track.id == TrackGenre.track_id, listed_tracks()))
            .group_by(Genre.id)
            .order_by(func.lower(Genre.name))
        )
        # the genre's three albums with the most of its songs (with a cover), for the genre tiles
        per_album = (
            select(TrackGenre.genre_id, Track.album_id, func.count().label("n"))
            .join(Track, and_(Track.id == TrackGenre.track_id, listed_tracks()))
            .join(Album, and_(Album.id == Track.album_id, Album.cover_path.is_not(None)))
            .group_by(TrackGenre.genre_id, Track.album_id)
            .subquery()
        )
        rank = func.row_number().over(partition_by=per_album.c.genre_id, order_by=(per_album.c.n.desc(), per_album.c.album_id))
        ranked = select(per_album.c.genre_id, per_album.c.album_id, rank.label("rn")).subquery()
        covers: dict[int, list[dict]] = {}
        for genre_id, album_id, v in db.execute(
            select(ranked.c.genre_id, ranked.c.album_id, Album.cover_version)
            .join(Album, Album.id == ranked.c.album_id)
            .where(ranked.c.rn <= 3)
            .order_by(ranked.c.genre_id, ranked.c.rn)
        ):
            covers.setdefault(genre_id, []).append({"id": album_id, "v": v})
        return {
            "items": [
                {"id": i, "name": n, "track_count": c, "covers": covers.get(i, [])} for i, n, c in rows
            ]
        }

    return shared_json(request, db, "genres", build)


@router.get("/library/version")
def get_library_version(_: User = Depends(current_user), db: Session = Depends(get_db)):
    """Goes up when the library changes; the app reloads lists it kept when it differs."""
    return {"version": library_version(db)}


def track_file(db: Session, track_id: int) -> tuple[Track, str]:
    """The track and its file on disk, or 404."""
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
    return track, path


@router.get("/tracks/{track_id}/stream")
def stream(track_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    track, path = track_file(db, track_id)
    media_type = AUDIO_TYPES.get(track.format) or mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/tracks/{track_id}/lyrics")
def lyrics(track_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    """{"synced": [[seconds, line], ...] | null, "plain": str | null}, read from the file each time."""
    _, path = track_file(db, track_id)
    return JSONResponse(read_lyrics(Path(path)), headers={"Cache-Control": "private, max-age=600"})
