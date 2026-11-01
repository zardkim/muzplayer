"""Numbers for the admin statistics page: the library, the people, what was played, the disk.

Plays per day and the top lists come from play_history, which keeps each person's latest 1000
plays (api/me.py HISTORY_KEEP); play counts (all time) from play_counts.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import Date, Integer, cast, func, select, text
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    Album, Artist, Book, FetchedLyrics, Genre, Playlist, PlayCount, PlayHistory, Track, TrackGenre, User,
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
    return {"days": DAYS, "library": library, "users": users, "plays": plays, "storage": storage}
