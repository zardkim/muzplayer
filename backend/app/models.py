from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    literal_column,
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
    # signed up and waiting for an admin to approve (can't log in meanwhile; api/auth.py signup)
    pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # off: plays leave no history or play count (listening privately)
    record_history: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # home screen rows in order, each shown or not: [{"key": "recent", "on": true}, ...]; NULL = default
    home_sections: Mapped[list | None] = mapped_column(JSON)
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
    __table_args__ = (
        Index("ix_artists_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        Index("ix_artists_search_text", "search_text", postgresql_using="gin", postgresql_ops={"search_text": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), unique=True)
    sort_name: Mapped[str] = mapped_column(String(500), default="")
    bio: Mapped[str | None] = mapped_column(Text)
    # where the photo came from: folder:<rel> (artist.jpg in the artist folder) | deezer:<id> | none
    # (an admin removed it: not looked up again); NULL = no photo yet
    image_path: Mapped[str | None] = mapped_column(String(500))
    image_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # in the URL: new photo, new URL
    image_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # last Deezer lookup
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")  # search_index.py


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        UniqueConstraint("kind", "album_artist_id", "title", postgresql_nulls_not_distinct=True),
        Index("ix_albums_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_albums_search_text", "search_text", postgresql_using="gin", postgresql_ops={"search_text": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # album | unofficial | compilation | soundtrack | chart (chart albums only hold covers for chart tracks)
    kind: Mapped[str] = mapped_column(String(16), default="album", server_default="album")
    title: Mapped[str] = mapped_column(String(500))
    album_artist_id: Mapped[int | None] = mapped_column(ForeignKey("artists.id", ondelete="SET NULL"), index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    # the full release date when a tag has one (YYYY-MM-DD): "on this day" on the home screen
    release_date: Mapped[date | None] = mapped_column(Date)
    # hires | lossless | NULL, from its songs (scanner.update_album_quality)
    quality: Mapped[str | None] = mapped_column(String(16))
    cover_path: Mapped[str | None] = mapped_column(String(500))
    # bumped whenever the cover is remade: it is part of the cover URL, so browsers can keep covers for good
    cover_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # what the cover was made from ("folder:<rel>" or "file:<rel>", relative to MUSIC_DIR) and its mtime then
    cover_source: Mapped[str | None] = mapped_column(Text)
    cover_mtime: Mapped[float | None] = mapped_column(Float)
    # the album's introduction: from an eztag report in its folder, or fetched from Bugs/Melon
    # (album_notes.py), or written by an admin; description_source says which ("eztag", "bugs:<id>", ...)
    description: Mapped[str | None] = mapped_column(Text)
    description_source: Mapped[str | None] = mapped_column(String(200))
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")  # title and artist (search_index.py)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        Index("ix_tracks_search_text", "search_text", postgresql_using="gin", postgresql_ops={"search_text": "gin_trgm_ops"}),
        Index("ix_tracks_title_lower", func.lower(literal_column("title")), "id"),
    )

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
    # title, artists and album as search matches them (search_index.py), with a trigram index
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    tag_json: Mapped[dict | None] = mapped_column(JSON)
    # album kind the tags say (scanner.tag_kind): compilation | unofficial | '' ; NULL = not worked out yet
    tag_kind: Mapped[str | None] = mapped_column(String(16))
    # from the file header; 0 = unknown, NULL = not read yet. bit_depth only for lossless files
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    bit_depth: Mapped[int | None] = mapped_column(SmallInteger)
    bitrate: Mapped[int | None] = mapped_column(Integer)  # kbps
    # ReplayGain from the tags (dB, and the peak as a fraction of full scale); NULL when untagged
    rg_track_gain: Mapped[float | None] = mapped_column(Float)
    rg_track_peak: Mapped[float | None] = mapped_column(Float)
    rg_album_gain: Mapped[float | None] = mapped_column(Float)
    rg_album_peak: Mapped[float | None] = mapped_column(Float)
    # synced lyrics (LRC) in the tags (NULL = not looked at yet), and a Song.lrc next to the file
    lrc_tag: Mapped[bool | None] = mapped_column(Boolean)
    lrc_file: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    chart_id: Mapped[int | None] = mapped_column(ForeignKey("charts.id", ondelete="SET NULL"), index=True)
    chart_position: Mapped[int | None] = mapped_column(Integer)
    # set on a duplicate copy (e.g. the same song in an older chart week): lists show only the canonical one
    canonical_track_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL"), index=True
    )
    missing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


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


class FetchedLyrics(Base):
    """Lyrics looked up for a song without its own (lyrics_fetch.py). lrc NULL: none were found."""

    __tablename__ = "fetched_lyrics"

    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    lrc: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(32))  # alsong | bugs | lrclib
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NameAlias(Base):
    """A merged duplicate (merge.py): songs tagged with `name` are filed under `target` instead,
    now and in later scans (the library is read-only, so the tags themselves stay as they are)."""

    __tablename__ = "name_aliases"

    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # artist | genre
    name: Mapped[str] = mapped_column(String(500), primary_key=True)
    target: Mapped[str] = mapped_column(String(500))
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
    # manual: tracks put in by hand; smart: rules (see smart.py) worked out each time it is opened
    kind: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    rules: Mapped[dict | None] = mapped_column(JSON)
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
    folder: Mapped[str | None] = mapped_column(Text)  # one top-level folder (NFC); NULL = the whole library
    mode: Mapped[str] = mapped_column(String(8), default="scan", server_default="scan")  # scan | rescan | reset


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
    cover_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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


class LibraryState(Base):
    """One row. version goes up whenever what the library lists show changes (scan, folder kinds,
    banners); cached responses and ETags are keyed on it."""

    __tablename__ = "library_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    # how the search index was built (search_index.SEARCH_VERSION); a different one is rebuilt
    search_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrackRating(Base):
    """A user's 1-5 stars for a song."""

    __tablename__ = "track_ratings"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 10", name="ck_track_ratings_rating"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True, index=True)
    rating: Mapped[int] = mapped_column(SmallInteger)  # half stars: 1-10 (the API speaks stars, 0.5-5)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AlbumRating(Base):
    """A user's 1-5 stars for an album (its own, not the average of its songs)."""

    __tablename__ = "album_ratings"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 10", name="ck_album_ratings_rating"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True, index=True)
    rating: Mapped[int] = mapped_column(SmallInteger)  # half stars: 1-10 (the API speaks stars, 0.5-5)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AlbumFavorite(Base):
    """A liked album (liked songs are Favorite)."""

    __tablename__ = "album_favorites"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlayCount(Base):
    """How often a user played a song, kept for good (play_history keeps only the latest plays)."""

    __tablename__ = "play_counts"
    __table_args__ = (
        Index("ix_play_counts_user_plays", "user_id", "plays"),
        Index("ix_play_counts_user_last", "user_id", "last_played_at"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True, index=True)
    plays: Mapped[int] = mapped_column(Integer, default=0)
    last_played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Video(Base):
    """A music video: a YouTube video added to an album or a song, or a video file on the NAS
    (library/video, file_path relative to it; a song or album is optional). Shared by everyone."""

    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint(
            "(youtube_id IS NOT NULL AND file_path IS NULL AND num_nonnulls(album_id, track_id) = 1)"
            " OR (file_path IS NOT NULL AND youtube_id IS NULL AND num_nonnulls(album_id, track_id) <= 1)",
            name="ck_videos_source",
        ),
        UniqueConstraint("album_id", "youtube_id"),
        UniqueConstraint("track_id", "youtube_id"),
        UniqueConstraint("file_path"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    album_id: Mapped[int | None] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), index=True)
    track_id: Mapped[int | None] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), index=True)
    youtube_id: Mapped[str | None] = mapped_column(String(16))
    file_path: Mapped[str | None] = mapped_column(String(1000))
    kind: Mapped[str] = mapped_column(String(16))  # mv | concert | tv | fan | other
    title: Mapped[str] = mapped_column(String(500))
    channel: Mapped[str] = mapped_column(String(200), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
