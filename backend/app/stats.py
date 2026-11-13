"""Numbers for the admin statistics page: the library, the people, what was played, the disk, the
audiobooks (their listening: book_progress) and the music videos (favorites and playlists: plays of
videos aren't recorded).

Plays per day and the top lists come from play_history, which keeps each person's latest 1000
plays (api/me.py HISTORY_KEEP); play counts (all time) from play_counts.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import Date, Integer, case, cast, func, select, text
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    Album, Artist, Book, BookProgress, FetchedLyrics, Genre, Playlist, PlayCount, PlayHistory, Track, TrackGenre, User,
    Video, VideoFavorite, VideoPlaylist, VideoPlaylistItem,
)

DAYS = 30


def _dir_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def collect(db: Session) -> dict:
    tz = os.environ.get("TZ") or "Asia/Seoul"
    present = Track.missing_at.is_(None)
    listed = (present, Track.canonical_track_id.is_(None))

    # ---- library ----
    tracks, seconds, size = db.execute(
        select(func.count(), func.coalesce(func.sum(Track.duration), 0), func.coalesce(func.sum(Track.file_size), 0)).where(*listed)
    ).one()
    formats = [
        {"format": f or "?", "tracks": n, "bytes": int(b or 0)}
        for f, n, b in db.execute(
            select(Track.format, func.count(), func.sum(Track.file_size)).where(*listed).group_by(Track.format).order_by(func.count().desc())
        )
    ]
    quality = dict(db.execute(select(func.coalesce(Album.quality, "lossy"), func.count()).where(Album.kind != "chart").group_by(Album.quality)).all())
    library = {
        "tracks": tracks,
        "hours": round(float(seconds) / 3600, 1),
        "bytes": int(size),
        "albums": db.scalar(select(func.count()).select_from(Album).where(Album.kind != "chart")),
        "artists": db.scalar(select(func.count()).select_from(Artist)),
        "genres": db.scalar(select(func.count()).select_from(Genre)),
        "books": db.scalar(select(func.count()).select_from(Book).where(Book.missing_at.is_(None))),
        "missing": db.scalar(select(func.count()).select_from(Track).where(Track.missing_at.is_not(None))),
        "damaged": db.scalar(select(func.count()).select_from(Track).where(present, Track.tag_json.op("->>")("_damaged").is_not(None))),
        "no_genre": db.scalar(select(func.count()).select_from(Track).where(*listed, ~select(TrackGenre.track_id).where(TrackGenre.track_id == Track.id).exists())),
        "with_notes": db.scalar(select(func.count()).select_from(Album).where(Album.description.is_not(None))),
        "fetched_lyrics": db.scalar(select(func.count()).select_from(FetchedLyrics).where(FetchedLyrics.lrc.is_not(None))),
        "formats": formats,
        "quality": {"hires": quality.get("hires", 0), "lossless": quality.get("lossless", 0), "lossy": quality.get("lossy", 0)},
    }

    # ---- people ----
    since = datetime.now().astimezone() - timedelta(days=DAYS)
    week = datetime.now().astimezone() - timedelta(days=7)
    users = {
        "total": db.scalar(select(func.count()).select_from(User)),
        "active": db.scalar(select(func.count()).select_from(User).where(User.is_active)),
        "admins": db.scalar(select(func.count()).select_from(User).where(User.is_admin)),
        "pending": db.scalar(select(func.count()).select_from(User).where(User.pending)),
        "seen_week": db.scalar(select(func.count()).select_from(User).where(User.last_login_at >= week)),
        "playlists": db.scalar(select(func.count()).select_from(Playlist)),
    }

    # ---- plays (last DAYS days) ----
    local_day = cast(func.timezone(tz, PlayHistory.played_at), Date)
    by_day = dict(db.execute(select(local_day, func.count()).where(PlayHistory.played_at >= since).group_by(local_day)).all())
    today = datetime.now().astimezone().date()
    days = [{"day": (today - timedelta(days=i)).isoformat(), "plays": by_day.get(today - timedelta(days=i), 0)} for i in range(DAYS - 1, -1, -1)]
    recent = select(PlayHistory.track_id, PlayHistory.user_id).where(PlayHistory.played_at >= since).subquery()
    top_tracks = [
        {"id": i, "title": title, "artist": artist, "plays": n}
        for i, title, artist, n in db.execute(
            select(Track.id, Track.title, Track.artist_text, func.count())
            .join(recent, recent.c.track_id == Track.id).group_by(Track.id).order_by(func.count().desc()).limit(10)
        )
    ]
    top_artists = [
        {"id": i, "name": name, "plays": n}
        for i, name, n in db.execute(
            select(Artist.id, Artist.name, func.count())
            .join(Track, Track.artist_id == Artist.id).join(recent, recent.c.track_id == Track.id)
            .group_by(Artist.id).order_by(func.count().desc()).limit(10)
        )
    ]
    per_user = [
        {"id": i, "name": name or username, "plays": n, "hours": round(float(secs or 0) / 3600, 1)}
        for i, name, username, n, secs in db.execute(
            select(User.id, User.display_name, User.username, func.count(), func.sum(Track.duration))
            .join(recent, recent.c.user_id == User.id).join(Track, Track.id == recent.c.track_id)
            .group_by(User.id).order_by(func.count().desc())
        )
    ]
    plays = {
        "days": days,
        "last_days": sum(d["plays"] for d in days),
        "hours": round(sum(u["hours"] for u in per_user), 1),
        "all_time": int(db.scalar(select(func.coalesce(func.sum(cast(PlayCount.plays, Integer)), 0))) or 0),
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "per_user": per_user,
    }

    # ---- disk (this app's own files) ----
    storage = {
        "database": int(db.scalar(text("SELECT pg_database_size(current_database())")) or 0),
        "covers": _dir_size(settings.cover_dir),  # album covers and artist photos
        "transcode": _dir_size(settings.data_dir / "transcode"),
    }
    return {
        "days": DAYS, "library": library, "users": users, "plays": plays, "storage": storage,
        "books": _books(db, since), "videos": _videos(db, since),
    }


def _books(db: Session, since: datetime) -> dict:
    """The audiobook library and its listening (book_progress: each person's place in each book)."""
    here = Book.missing_at.is_(None)
    count, seconds = db.execute(select(func.count(), func.coalesce(func.sum(Book.duration), 0)).where(here)).one()
    size = sum(int(f.get("size") or 0) for (files,) in db.execute(select(Book.files).where(here)) for f in files or [])
    authors = {a.strip() for (a,) in db.execute(select(Book.authors).where(here)) for a in (a or "").split(",") if a.strip()}
    series = db.scalar(select(func.count(func.distinct(Book.series))).where(here, Book.series != ""))
    chapters = sum(len(c or []) for (c,) in db.execute(select(Book.chapters).where(here)))
    listened = func.least(BookProgress.position, Book.duration)  # (a place past the end counts as the whole book)
    started = (BookProgress.position > 0) | BookProgress.finished
    progress = db.execute(
        select(
            func.count(func.distinct(BookProgress.user_id)),
            func.count().filter(started & ~BookProgress.finished),
            func.count().filter(BookProgress.finished),
            func.coalesce(func.sum(case((BookProgress.finished, Book.duration), else_=listened)), 0),
            func.count().filter(BookProgress.updated_at >= since),
        ).join(Book, Book.id == BookProgress.book_id).where(started)
    ).one()
    top = [
        {"id": i, "title": title, "authors": authors_, "listeners": n, "finished": f}
        for i, title, authors_, n, f in db.execute(
            select(Book.id, Book.title, Book.authors, func.count(), func.count().filter(BookProgress.finished))
            .join(BookProgress, BookProgress.book_id == Book.id).where(here, started)
            .group_by(Book.id).order_by(func.count().desc(), Book.title).limit(10)
        )
    ]
    per_user = [
        {"id": i, "name": name or username, "books": n, "finished": f, "hours": round(float(secs or 0) / 3600, 1)}
        for i, name, username, n, f, secs in db.execute(
            select(User.id, User.display_name, User.username, func.count(), func.count().filter(BookProgress.finished),
                   func.sum(case((BookProgress.finished, Book.duration), else_=listened)))
            .join(BookProgress, BookProgress.user_id == User.id).join(Book, Book.id == BookProgress.book_id).where(started)
            .group_by(User.id).order_by(func.count().desc())
        )
    ]
    return {
        "books": count, "hours": round(float(seconds) / 3600, 1), "bytes": size, "authors": len(authors), "series": series or 0,
        "chapters": chapters, "listeners": progress[0], "in_progress": progress[1], "finished": progress[2],
        "listened_hours": round(float(progress[3]) / 3600, 1), "active_days": progress[4], "top": top, "per_user": per_user,
    }


def _videos(db: Session, since: datetime) -> dict:
    """The music videos: where from (YouTube or the NAS), what kind, and how they are kept (favorites,
    video playlists)."""
    count, youtube, local, seconds = db.execute(
        select(func.count(), func.count().filter(Video.youtube_id.is_not(None)), func.count().filter(Video.file_path.is_not(None)),
               func.coalesce(func.sum(Video.duration), 0))
    ).one()
    kinds = [{"kind": k, "videos": n} for k, n in db.execute(select(Video.kind, func.count()).group_by(Video.kind).order_by(func.count().desc()))]
    top = [
        {"id": i, "title": title, "channel": channel, "youtube": bool(yt), "likes": n}
        for i, title, channel, yt, n in db.execute(
            select(Video.id, Video.title, Video.channel, Video.youtube_id, func.count())
            .join(VideoFavorite, VideoFavorite.video_id == Video.id).group_by(Video.id).order_by(func.count().desc(), Video.title).limit(10)
        )
    ]
    channels = [
        {"name": c, "videos": n}
        for c, n in db.execute(
            select(Video.channel, func.count()).where(Video.channel != "").group_by(Video.channel).order_by(func.count().desc()).limit(10)
        )
    ]
    return {
        "videos": count, "youtube": youtube, "local": local, "local_hours": round(float(seconds) / 3600, 1),
        "with_album": db.scalar(select(func.count()).select_from(Video).where(Video.album_id.is_not(None))),
        "added_days": db.scalar(select(func.count()).select_from(Video).where(Video.created_at >= since)),
        "favorites": db.scalar(select(func.count()).select_from(VideoFavorite)),
        "playlists": db.scalar(select(func.count()).select_from(VideoPlaylist)),
        "playlist_items": db.scalar(select(func.count()).select_from(VideoPlaylistItem)),
        "kinds": kinds, "top": top, "channels": channels,
    }
