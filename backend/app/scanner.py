"""Library scanner: reads tags from MUSIC_DIR into the DB. Never modifies music files."""

import io
import logging
import os
import re
import threading
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import mutagen
from PIL import Image
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, defer

from .config import settings
from .db import SessionLocal
from .models import Album, Artist, Genre, ScanJob, Track, TrackGenre

log = logging.getLogger(__name__)

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".mp4", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wma", ".ape", ".aif", ".aiff"}
FOLDER_COVERS = ("cover", "folder", "front", "album")
COVER_SIZES = {"thumb": 300, "large": 1000}
BATCH = 200

_lock = threading.Lock()

# tag name candidates, compared case-insensitively (ID3/MP4 via easy mode, Vorbis, APE, ASF)
TAG_KEYS = {
    "title": ("title", "wm/title"),
    "artist": ("artist", "author"),
    "album": ("album", "wm/albumtitle"),
    "albumartist": ("albumartist", "album artist", "album_artist", "wm/albumartist"),
    "tracknumber": ("tracknumber", "track", "wm/tracknumber"),
    "discnumber": ("discnumber", "disc", "disk", "wm/partofset"),
    "date": ("date", "year", "originaldate", "wm/year"),
    "genre": ("genre", "wm/genre"),
}


def nfc(value: str | None) -> str:
    return unicodedata.normalize("NFC", value).strip() if value else ""


def _text_values(value) -> list[str]:
    items = value if isinstance(value, list) else [value]
    out = []
    for item in items:
        text = getattr(item, "value", item)
        if isinstance(text, bytes):
            continue
        text = nfc(str(text))
        if text:
            out.append(text)
    return out


def _read_tags(path: Path) -> tuple[dict[str, list[str]], float | None]:
    audio = mutagen.File(path, easy=True)
    if audio is None:
        raise ValueError("unsupported file")
    raw: dict[str, list[str]] = {}
    for key, value in (audio.tags or {}).items():
        values = _text_values(value)
        if values:
            raw[str(key).lower()] = values
    duration = getattr(audio.info, "length", None)
    return raw, duration


def _pick(raw: dict[str, list[str]], field: str) -> list[str]:
    for key in TAG_KEYS[field]:
        if raw.get(key):
            return raw[key]
    return []


def _first(raw: dict[str, list[str]], field: str) -> str:
    values = _pick(raw, field)
    return values[0] if values else ""


def _number(text: str) -> int | None:
    match = re.match(r"\s*(\d+)", text or "")
    return int(match.group(1)) if match else None


def _year(text: str) -> int | None:
    match = re.search(r"(\d{4})", text or "")
    return int(match.group(1)) if match else None


def _embedded_cover(path: Path) -> bytes | None:
    try:
        audio = mutagen.File(path)
    except Exception:
        return None
    if audio is None:
        return None
    pictures = getattr(audio, "pictures", None)  # FLAC
    if pictures:
        return pictures[0].data
    tags = audio.tags
    if tags is None:
        return None
    if hasattr(tags, "getall"):  # ID3
        apic = tags.getall("APIC")
        if apic:
            return apic[0].data
    covr = tags.get("covr") if hasattr(tags, "get") else None  # MP4
    if covr:
        return bytes(covr[0])
    return None


def _folder_cover(directory: Path) -> bytes | None:
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None
    for name in FOLDER_COVERS:
        for entry in entries:
            if entry.stem.lower() == name and entry.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                return entry.read_bytes()
    return None


def cover_file(album_id: int, size: str) -> Path:
    return settings.cover_dir / f"{album_id}_{COVER_SIZES[size]}.jpg"


def _save_cover(album_id: int, data: bytes) -> bool:
    try:
        image = Image.open(io.BytesIO(data))
        image = image.convert("RGB")
    except Exception:
        return False
    settings.cover_dir.mkdir(parents=True, exist_ok=True)
    for size in COVER_SIZES:
        copy = image.copy()
        copy.thumbnail((COVER_SIZES[size], COVER_SIZES[size]))
        copy.save(cover_file(album_id, size), "JPEG", quality=85)
    return True


class _Cache:
    """Keeps artist/album/genre ids in memory during one scan."""

    def __init__(self, db: Session):
        self.db = db
        self.artists = {a.name: a.id for a in db.scalars(select(Artist))}
        self.albums = {(a.album_artist_id, a.title): a for a in db.scalars(select(Album))}
        self.genres = {g.name: g.id for g in db.scalars(select(Genre))}

    def artist(self, name: str) -> int | None:
        if not name:
            return None
        if name not in self.artists:
            row = Artist(name=name, sort_name=name.lower())
            self.db.add(row)
            self.db.flush()
            self.artists[name] = row.id
        return self.artists[name]

    def album(self, title: str, artist_id: int | None, year: int | None) -> Album:
        key = (artist_id, title)
        if key not in self.albums:
            row = Album(title=title, album_artist_id=artist_id, year=year)
            self.db.add(row)
            self.db.flush()
            self.albums[key] = row
        album = self.albums[key]
        if album.year is None and year:
            album.year = year
        return album

    def genre(self, name: str) -> int:
        if name not in self.genres:
            row = Genre(name=name)
            self.db.add(row)
            self.db.flush()
            self.genres[name] = row.id
        return self.genres[name]


def _apply_tags(db: Session, cache: _Cache, track: Track, path: Path, cover_tries: dict[int, int]) -> None:
    raw, duration = _read_tags(path)
    rel = Path(track.file_path)

    title = _first(raw, "title") or nfc(rel.stem)
    artist_text = " / ".join(_pick(raw, "artist"))
    album_title = _first(raw, "album") or nfc(rel.parent.name) or ""
    album_artist = _first(raw, "albumartist") or (_pick(raw, "artist") or [""])[0]
    year = _year(_first(raw, "date"))

    track.title = title[:1000]
    track.artist_text = artist_text[:1000]
    track.artist_id = cache.artist((_pick(raw, "artist") or [""])[0][:500])
    album = cache.album(album_title[:500], cache.artist(album_artist[:500]), year)
    track.album_id = album.id
    track.track_no = _number(_first(raw, "tracknumber"))
    track.disc_no = _number(_first(raw, "discnumber"))
    track.duration = duration
    track.tag_json = {k: v[:5] for k, v in raw.items() if len(k) < 64}
    db.flush()

    genre_ids = {cache.genre(g[:200]) for g in _pick(raw, "genre")}
    db.execute(delete(TrackGenre).where(TrackGenre.track_id == track.id))
    for genre_id in genre_ids:
        db.add(TrackGenre(track_id=track.id, genre_id=genre_id))

    # try a few tracks per album: the first one may simply have no embedded art
    tries = cover_tries.get(album.id, 0)
    if tries < 3:
        if cover_file(album.id, "thumb").exists():
            cover_tries[album.id] = 3
            album.cover_path = cover_file(album.id, "thumb").name
            return
        cover_tries[album.id] = tries + 1
        data = _embedded_cover(path) or _folder_cover(path.parent)
        if data and _save_cover(album.id, data):
            cover_tries[album.id] = 3
            album.cover_path = cover_file(album.id, "thumb").name


def _walk(root: Path, on_error):
    """Yields audio files under root, following symlinked folders and mounts.

    Folder loops (a link pointing at its own parent) are visited once.
    on_error(path, exc) is called for folders that can't be read and for broken links.
    """
    stack = [root]
    visited: set[tuple[int, int]] = set()
    while stack:
        directory = stack.pop()
        try:
            st = os.stat(directory)
            if (st.st_dev, st.st_ino) in visited:
                continue
            visited.add((st.st_dev, st.st_ino))
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError as exc:
            on_error(directory, exc)
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir(follow_symlinks=True):
                    if not entry.name.startswith("@"):  # Synology @eaDir etc.
                        stack.append(Path(entry.path))
                    continue
                if entry.is_symlink() and not os.path.exists(entry.path):
                    on_error(Path(entry.path), FileNotFoundError(2, "broken link"))
                    continue
            except OSError as exc:
                on_error(Path(entry.path), exc)
                continue
            if os.path.splitext(entry.name)[1].lower() in AUDIO_EXTS:
                yield Path(entry.path)


def _collect(root: Path, existing: dict[str, Track], on_error) -> list[tuple[str, Path]]:
    """Lists (relative path, path) pairs, one per real file.

    The same file reachable through two links is indexed once, preferring the path
    already in the DB so playlists keep pointing at it.
    """
    by_real: dict[str, list[tuple[str, Path]]] = {}
    for path in _walk(root, on_error):
        rel = os.path.relpath(path, root)
        try:
            rel.encode("utf-8")
        except UnicodeEncodeError:
            on_error(path, ValueError("invalid file name encoding"))
            continue
        by_real.setdefault(os.path.realpath(path), []).append((rel, path))
    files = []
    for candidates in by_real.values():
        known = [c for c in candidates if c[0] in existing]
        files.append(min(known or candidates))
    return files


def _run(job_id: int) -> None:
    db = SessionLocal()
    job = db.get(ScanJob, job_id)
    errors: list[str] = []
    try:
        root = settings.music_dir
        if not root.is_dir():
            raise RuntimeError(f"music_dir_not_found: {root}")
        cache = _Cache(db)
        existing = {t.file_path: t for t in db.scalars(select(Track).options(defer(Track.tag_json)))}
        unavailable: list[str] = []  # folders we could not read: keep their tracks as they are
        cover_tries: dict[int, int] = {}
        pending = 0

        def on_error(path: Path, exc: Exception) -> None:
            # usually PUID/PGID lacking permission, an unmounted share or a broken link
            job.errors += 1
            unavailable.append(os.path.relpath(path, root))
            if len(errors) < 50:
                errors.append(f"cannot read: {path}: {getattr(exc, 'strerror', None) or exc}")

        files = _collect(root, existing, on_error)
        if not files and any(t.missing_at is None for t in existing.values()):
            # an empty library is almost always an unmounted folder; don't hide everything
            raise RuntimeError(f"library_empty: no audio files found under {root}")
        seen = {rel for rel, _ in files}

        for rel, path in files:
            job.scanned += 1
            try:
                st = path.stat()
                track = existing.get(rel)
                if track and track.file_size == st.st_size and track.file_mtime == st.st_mtime:
                    if track.missing_at is not None:
                        track.missing_at = None
                        job.updated += 1
                    continue
                is_new = track is None
                with db.begin_nested():
                    if is_new:
                        track = Track(
                            file_path=rel, title="", file_size=st.st_size, file_mtime=st.st_mtime,
                            format=path.suffix.lower().lstrip("."),
                        )
                        db.add(track)
                        db.flush()
                    else:
                        track.file_size = st.st_size
                        track.file_mtime = st.st_mtime
                        track.missing_at = None
                    _apply_tags(db, cache, track, path, cover_tries)
                existing[rel] = track
                if is_new:
                    job.added += 1
                else:
                    job.updated += 1
            except Exception as exc:  # one bad file must not stop the scan
                job.errors += 1
                if len(errors) < 50:
                    errors.append(f"{rel}: {exc}")
                # rows created inside the rolled-back savepoint are gone; reload ids
                cache = _Cache(db)
            pending += 1
            if pending >= BATCH:
                db.commit()
                pending = 0

        def reachable(rel: str) -> bool:
            return not any(u == "." or rel == u or rel.startswith(u + os.sep) for u in unavailable)

        now = datetime.now(UTC)
        gone = [
            t.id
            for path_key, t in existing.items()
            if path_key not in seen and t.missing_at is None and reachable(path_key)
        ]
        for i in range(0, len(gone), 1000):
            db.execute(update(Track).where(Track.id.in_(gone[i : i + 1000])).values(missing_at=now))
        job.missing = len(gone)
        job.status = "done"
    except Exception as exc:
        log.exception("scan failed")
        db.rollback()
        job = db.get(ScanJob, job_id)
        job.status = "failed"
        errors.append(str(exc))
    finally:
        job.finished_at = datetime.now(UTC)
        job.error_summary = "\n".join(errors) or None
        db.commit()
        db.close()
        _lock.release()


def start_scan(db: Session) -> ScanJob | None:
    """Starts a background scan. Returns None when one is already running."""
    if not _lock.acquire(blocking=False):
        return None
    job = ScanJob(status="running")
    db.add(job)
    db.commit()
    threading.Thread(target=_run, args=(job.id,), daemon=True, name="scan").start()
    return job


def start_auto_scan(stop: threading.Event) -> None:
    """Rescans every SCAN_INTERVAL_MINUTES (first run one minute after start).

    Polling works the same for local folders, symlinked folders and network mounts,
    where file-change notifications are unreliable.
    """
    minutes = settings.scan_interval_minutes
    if minutes <= 0:
        return

    def loop() -> None:
        delay = 60
        while not stop.wait(delay):
            with SessionLocal() as db:
                if start_scan(db) is None:
                    log.info("auto scan skipped: a scan is already running")
            delay = minutes * 60

    threading.Thread(target=loop, daemon=True, name="auto-scan").start()


def mark_interrupted_jobs(db: Session) -> None:
    """A restart kills the scan thread; close out jobs left as running."""
    db.execute(
        update(ScanJob)
        .where(ScanJob.status == "running")
        .values(status="failed", finished_at=datetime.now(UTC), error_summary="interrupted")
    )
    db.commit()
