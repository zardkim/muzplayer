from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    __tablename__ = "sessions"

    # sha256 of the random token stored in the cookie
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), unique=True)
    sort_name: Mapped[str] = mapped_column(String(500), default="")
    bio: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(500))


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        UniqueConstraint("kind", "album_artist_id", "title", postgresql_nulls_not_distinct=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # album | unofficial | compilation | chart (chart albums only hold covers for chart tracks)
    kind: Mapped[str] = mapped_column(String(16), default="album", server_default="album")
    title: Mapped[str] = mapped_column(String(500))
    album_artist_id: Mapped[int | None] = mapped_column(ForeignKey("artists.id", ondelete="SET NULL"))
    year: Mapped[int | None] = mapped_column(Integer)
    cover_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    album_id: Mapped[int | None] = mapped_column(ForeignKey("albums.id", ondelete="SET NULL"), index=True)
    artist_id: Mapped[int | None] = mapped_column(ForeignKey("artists.id", ondelete="SET NULL"), index=True)
    artist_text: Mapped[str] = mapped_column(String(1000), default="")
    title: Mapped[str] = mapped_column(String(1000))
    track_no: Mapped[int | None] = mapped_column(Integer)
    disc_no: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[float | None] = mapped_column(Float)
    # relative to MUSIC_DIR, exactly as on disk (not normalized) so it can be opened
    file_path: Mapped[str] = mapped_column(Text, unique=True)
    file_size: Mapped[int] = mapped_column(BigInteger)
    file_mtime: Mapped[float] = mapped_column(Float)
    format: Mapped[str] = mapped_column(String(16))
    tag_json: Mapped[dict | None] = mapped_column(JSON)
    chart_id: Mapped[int | None] = mapped_column(ForeignKey("charts.id", ondelete="SET NULL"), index=True)
    chart_position: Mapped[int | None] = mapped_column(Integer)
    # set on a duplicate copy (e.g. the same song in an older chart week): lists show only the canonical one
    canonical_track_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL"), index=True
    )
    missing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LibraryFolder(Base):
    """Kind of a top-level folder of the library. Folders without a row are "album"."""

    __tablename__ = "library_folders"

    path: Mapped[str] = mapped_column(String(500), primary_key=True)  # folder name, NFC
    kind: Mapped[str] = mapped_column(String(16))  # compilation | chart | excluded
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chart(Base):
    """One collection: a chart week under a "chart" top-level folder, or a theme
    (e.g. "카페에서 듣기 좋은 노래") under a "theme" one. Either is a folder with audio files."""

    __tablename__ = "charts"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="chart", server_default="chart")  # chart | theme
    folder_path: Mapped[str] = mapped_column(Text, unique=True)  # relative, as on disk
    # chart: where it comes from (멜론, 벅스); theme: its category folder (팝송), may be empty
    source: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(500))  # folder name
    banner_file: Mapped[str | None] = mapped_column(Text)  # banner.jpg in the folder, relative to MUSIC_DIR
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class TrackGenre(Base):
    __tablename__ = "track_genres"

    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (Index("ix_playlist_tracks_playlist_position", "playlist_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"))
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlayHistory(Base):
    __tablename__ = "play_history"
    __table_args__ = (Index("ix_play_history_user_played", "user_id", "played_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | done | failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scanned: Mapped[int] = mapped_column(Integer, default=0)
    added: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    missing: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    books_added: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    books_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    books_missing: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Book(Base):
    """One audiobook: a folder of audio files under AUDIOBOOK_DIR (or a single file at its top)."""

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    # relative to AUDIOBOOK_DIR, NFC: the book's identity (also matches Audiobookshelf's relPath)
    folder_path: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(String(1000))
    subtitle: Mapped[str] = mapped_column(String(1000), default="")
    authors: Mapped[str] = mapped_column(String(1000), default="")
    narrators: Mapped[str] = mapped_column(String(1000), default="")
    series: Mapped[str] = mapped_column(String(500), default="")
    series_seq: Mapped[str] = mapped_column(String(32), default="")
    genres: Mapped[list] = mapped_column(JSON, default=list)
    published_year: Mapped[int | None] = mapped_column(Integer)
    publisher: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    isbn: Mapped[str] = mapped_column(String(32), default="")
    asin: Mapped[str] = mapped_column(String(32), default="")
    language: Mapped[str] = mapped_column(String(64), default="")
    duration: Mapped[float] = mapped_column(Float, default=0)
    # [{"start", "end", "title"}], seconds on the whole-book timeline
    chapters: Mapped[list] = mapped_column(JSON, default=list)
    # [{"path" (relative, as on disk), "size", "mtime", "duration", "offset"}] in play order
    files: Mapped[list] = mapped_column(JSON, default=list)
    cover_sig: Mapped[str] = mapped_column(String(1000), default="")  # folder image it came from
    has_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    # field names set by an import or by hand; a rescan never overwrites them from tags
    locked: Mapped[list] = mapped_column(JSON, default=list)
    abs_id: Mapped[str | None] = mapped_column(String(64))
    missing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BookProgress(Base):
    __tablename__ = "book_progress"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True, index=True)
    position: Mapped[float] = mapped_column(Float, default=0)  # seconds on the whole-book timeline
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Banner(Base):
    """An AI-made banner image, kept by folder (or chart source) rather than by chart row:
    chart rows go away when their files do, and the banner should be there when they return."""

    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True)  # "folder:<folder_path>" | "source:<chart source>"
    prompt: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
