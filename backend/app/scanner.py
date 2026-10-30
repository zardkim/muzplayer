"""Library scanner: reads tags from MUSIC_DIR into the DB. Never modifies music files."""

import io
import logging
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import mutagen
from PIL import Image
from sqlalchemy import delete, exists, func, insert, select, text, update
from sqlalchemy.orm import Session, defer

from .config import settings
from .db import SessionLocal
from .models import (
    Album, AlbumFavorite, AlbumRating, Artist, Chart, Genre, LibraryFolder, LibraryState, ScanJob, Track, TrackGenre,
    Video,
)

log = logging.getLogger(__name__)

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".mp4", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wma", ".ape", ".aif", ".aiff"}
FOLDER_COVERS = ("cover", "folder", "front", "album")
COVER_SIZES = {"thumb": 300, "large": 1000}
BATCH = 200

FOLDER_KINDS = ("album", "compilation", "chart", "theme", "excluded")
COLLECTION_KINDS = ("chart", "theme")  # folders of collections: each folder with audio files is one
UNOFFICIAL_DIRS = {"비정규", "unofficial"}  # compared casefolded, at any depth
VARIOUS_ARTISTS = "Various Artists"
# "001 Artist - Title.mp3": a short number then a separator; "2002.mp3" is a title, not a rank
RANK_PREFIX = re.compile(r"^\s*(\d{1,3})(?:[\s._\-)\]]+)")
DISC_DIR = re.compile(r"^(?:cd|disc|disk)\s*[-_.]?\s*(\d+)$", re.IGNORECASE)
BANNER_NAMES = ("banner.jpg", "banner.jpeg", "banner.png", "banner.webp")

_lock = threading.Lock()
_cancel = threading.Event()  # set by an admin's "stop scan"; checked between files


class ScanCancelled(Exception):
    pass


def check_cancel() -> None:
    if _cancel.is_set():
        raise ScanCancelled


def scan_running() -> bool:
    return _lock.locked()


def cancel_scan() -> bool:
    """Asks the running scan to stop after the current file. False when none is running."""
    if not _lock.locked():
        return False
    _cancel.set()
    return True

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


def _folder_cover(directory: Path) -> Path | None:
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None
    for name in FOLDER_COVERS:
        for entry in entries:
            if entry.stem.lower() == name and entry.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                return entry
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


def _set_album_cover(album: Album, data: bytes, source: str, mtime: float) -> bool:
    """Saves the cover and records where it came from; a new version gives it a new URL."""
    if not _save_cover(album.id, data):
        return False
    album.cover_path = cover_file(album.id, "thumb").name
    album.cover_version = (album.cover_version or 0) + 1
    album.cover_source, album.cover_mtime = source, mtime
    return True


def _cover_from_file(album: Album, path: Path, rel: str) -> bool:
    """The picture embedded in one audio file."""
    data = _embedded_cover(path)
    if not data:
        return False
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    return _set_album_cover(album, data, f"file:{rel}", mtime)


def _cover_from_folder(album: Album, root: Path, directory: Path) -> bool:
    """cover.jpg (folder.jpg, ...) next to the audio files."""
    image = _folder_cover(directory)
    if image is None:
        return False
    try:
        data, mtime = image.read_bytes(), image.stat().st_mtime
    except OSError:
        return False
    return _set_album_cover(album, data, f"folder:{os.path.relpath(image, root)}", mtime)


def search_key(*parts: str | None) -> str:
    """What search matches against: NFC, lowercased (the query is lowercased the same way)."""
    return nfc(" ".join(p for p in parts if p)).lower()


def folder_kinds(db: Session) -> dict[str, str]:
    """Top-level folder name (NFC) -> kind. Folders not listed are "album"."""
    return {f.path: f.kind for f in db.scalars(select(LibraryFolder))}


@dataclass(frozen=True)
class Placement:
    """Where a file belongs, decided by its path alone."""

    kind: str  # album kind: album | unofficial | compilation | chart (also for themes)
    chart_folder: str | None = None  # relative folder of the chart week or theme, as on disk
    chart_source: str = ""
    chart_kind: str = "chart"  # chart | theme


def placement(rel: str, kinds: dict[str, str]) -> Placement:
    parts = Path(rel).parts
    folder_kind = kinds.get(nfc(parts[0]), "album") if len(parts) > 1 else "album"
    if folder_kind in COLLECTION_KINDS:
        # 차트/멜론/2026-10-4주/001 x.mp3 -> source 멜론, chart 2026-10-4주
        # 테마/팝송/TOP100/CD1/001 x.mp3 -> category 팝송, theme TOP100 (disc folders merge)
        folders = list(parts[:-1])
        while len(folders) > 2 and DISC_DIR.match(nfc(folders[-1])):
            folders.pop()
        # a chart's source is the folder under the chart root; a theme's category needs one more level
        group = nfc(parts[1]) if len(folders) > (1 if folder_kind == "chart" else 2) else ""
        return Placement("chart", str(Path(*folders)), group, folder_kind)
    if folder_kind == "compilation":
        return Placement("compilation")
    if any(nfc(p).casefold() in UNOFFICIAL_DIRS for p in parts[:-1]):
        return Placement("unofficial")
    return Placement("album")


class _Cache:
    """Keeps artist/album/chart/genre ids in memory during one scan."""

    def __init__(self, db: Session, moves: dict[int, int] | None = None):
        self.db = db
        # old album id -> new one, for songs refiled to an album made anew (tags or folder kind
        # changed); the old album's stars, likes and videos follow when it is pruned
        self.moves: dict[int, int] = {} if moves is None else moves
        self.artists = {a.name: a.id for a in db.scalars(select(Artist))}
        self.albums = {(a.kind, a.album_artist_id, a.title): a for a in db.scalars(select(Album))}
        self.album_kinds = {a.id: a.kind for a in self.albums.values()}
        self.charts = {c.folder_path: c for c in db.scalars(select(Chart))}
        self.chart_folders = {c.id: k for k, c in self.charts.items()}
        self.genres = {g.name: g.id for g in db.scalars(select(Genre))}

    def matches(self, track: Track, place: Placement) -> bool:
        """Whether the track is already filed the way its path says."""
        return (
            self.album_kinds.get(track.album_id) == place.kind
            and self.chart_folders.get(track.chart_id) == place.chart_folder
            and (
                place.chart_folder is None
                or (self.charts[place.chart_folder].kind, self.charts[place.chart_folder].source)
                == (place.chart_kind, place.chart_source[:200])
            )
        )

    def artist(self, name: str) -> int | None:
        if not name:
            return None
        if name not in self.artists:
            row = Artist(name=name, sort_name=name.lower())
            self.db.add(row)
            self.db.flush()
            self.artists[name] = row.id
        return self.artists[name]

    def album(self, kind: str, title: str, artist_id: int | None, year: int | None) -> Album:
        key = (kind, artist_id, title)
        if key not in self.albums:
            row = Album(kind=kind, title=title, album_artist_id=artist_id, year=year)
            self.db.add(row)
            self.db.flush()
            self.albums[key] = row
            self.album_kinds[row.id] = kind
        album = self.albums[key]
        if album.year is None and year:
            album.year = year
        return album

    def chart(self, folder: str, source: str, kind: str) -> int:
        if folder not in self.charts:
            row = Chart(
                folder_path=folder, kind=kind, source=source[:200], title=(nfc(Path(folder).name) or source)[:500]
            )
            self.db.add(row)
            self.db.flush()
            self.charts[folder] = row
            self.chart_folders[row.id] = folder
        row = self.charts[folder]
        row.kind, row.source = kind, source[:200]  # the folder kind changed between chart and theme
        return row.id

    def genre(self, name: str) -> int:
        if name not in self.genres:
            row = Genre(name=name)
            self.db.add(row)
            self.db.flush()
            self.genres[name] = row.id
        return self.genres[name]


def _apply_tags(
    cache: _Cache,
    track: Track,
    raw: dict[str, list[str]],
    duration: float | None,
    path: Path,
    place: Placement,
    cover_tries: dict[int, int],
) -> None:
    track.artist_text = " / ".join(_pick(raw, "artist"))[:1000]
    track.artist_id = cache.artist((_pick(raw, "artist") or [""])[0][:500])
    track.track_no = _number(_first(raw, "tracknumber"))
    track.disc_no = _number(_first(raw, "discnumber"))
    track.duration = duration
    track.tag_json = {k: v[:5] for k, v in raw.items() if len(k) < 64}
    _classify(cache, track, raw, path, place, cover_tries)


# one new or changed file, read but not yet written: (rel, path, stat, placement, tags, duration)
Pending = tuple[str, Path, os.stat_result, Placement, dict[str, list[str]], float | None]


def _store(
    db: Session, cache: _Cache, existing: dict[str, Track], items: list[Pending], cover_tries: dict[int, int]
) -> list[tuple[str, Track, bool]]:
    """Writes a batch of read files with a few statements instead of several per file.
    Returns (rel, track, is_new) for each; existing is left alone until the caller commits."""
    done: list[tuple[str, Track, bool]] = []
    genres: list[tuple[Track, set[int]]] = []
    for rel, path, st, place, raw, duration in items:
        track = existing.get(rel)
        is_new = track is None
        if is_new:
            track = Track(file_path=rel, title="", file_size=st.st_size, file_mtime=st.st_mtime,
                          format=path.suffix.lower().lstrip("."))
            db.add(track)
        track.file_size, track.file_mtime, track.missing_at = st.st_size, st.st_mtime, None
        _apply_tags(cache, track, raw, duration, path, place, cover_tries)
        genres.append((track, {cache.genre(g[:200]) for g in _pick(raw, "genre")}))
        done.append((rel, track, is_new))
    db.flush()
    changed = [t.id for (_, t, is_new) in done if not is_new]
    if changed:
        # no ORM bookkeeping: with it, every delete walks every object loaded so far (slower as the scan goes)
        db.execute(
            delete(TrackGenre).where(TrackGenre.track_id.in_(changed)).execution_options(synchronize_session=False)
        )
    rows = [{"track_id": t.id, "genre_id": g} for t, ids in genres for g in ids]
    if rows:
        db.execute(insert(TrackGenre), rows)
    return done


def _classify(
    cache: _Cache, track: Track, raw: dict[str, list[str]], path: Path, place: Placement, cover_tries: dict[int, int]
) -> None:
    """Files the track under an album (and chart) of the kind its folder says; sets the title too,
    since an untagged file's title comes from its name, which depends on the kind.

    Also used without re-reading the file (raw = stored tag_json) when only a folder kind changed.
    """
    rel = Path(track.file_path)
    stem = nfc(rel.stem)
    if place.kind == "chart":  # "001 Artist - Title" -> "Artist - Title"
        stem = RANK_PREFIX.sub("", stem) or stem
    track.title = (_first(raw, "title") or stem)[:1000]
    album_title = _first(raw, "album") or nfc(rel.parent.name) or ""
    album_artist = _first(raw, "albumartist") or (
        VARIOUS_ARTISTS if place.kind == "compilation" else (_pick(raw, "artist") or [""])[0]
    )
    album = cache.album(place.kind, album_title[:500], cache.artist(album_artist[:500]), _year(_first(raw, "date")))
    if track.album_id is not None and track.album_id != album.id:
        cache.moves.setdefault(track.album_id, album.id)
    track.album_id = album.id
    track.search_text = search_key(track.title, track.artist_text, album.title)
    if place.chart_folder is not None:
        track.chart_id = cache.chart(place.chart_folder, place.chart_source, place.chart_kind)
        rank = RANK_PREFIX.match(rel.stem)
        track.chart_position = int(rank.group(1)) if rank else _number(_first(raw, "tracknumber"))
    else:
        track.chart_id = None
        track.chart_position = None
    _ensure_cover(album, path, track.file_path, cover_tries)


def _ensure_cover(album: Album, path: Path, rel: str, cover_tries: dict[int, int]) -> None:
    """A new album gets its cover from the first of its files that has one (a later change to
    that source is picked up by _refresh_covers)."""
    # try a few tracks per album: the first one may simply have no embedded art
    tries = cover_tries.get(album.id, 0)
    if tries >= 3 or album.cover_path:
        return
    cover_tries[album.id] = tries + 1
    root = settings.music_dir
    if _cover_from_file(album, path, rel) or _cover_from_folder(album, root, path.parent):
        cover_tries[album.id] = 3


def _refresh_covers(db: Session, root: Path, reachable, cover_tries: dict[int, int]) -> int:
    """Keeps covers in step with their files. Returns how many covers changed.

    - a cover whose source (cover.jpg, or the audio file it was embedded in) changed or went
      away is made again, from the album's files as for a new album
    - a cover from before 0.6 (source unknown) is made again once
    - an album without a cover looks for a cover.jpg added since
    Albums under folders that can't be read now are left alone.
    """
    work: list[Album] = []
    for album in db.scalars(select(Album)):
        if cover_tries.get(album.id, 0) >= 3 and album.cover_source:
            continue  # made during this scan
        if album.cover_path is None:
            work.append(album)
        elif album.cover_source is None:
            work.append(album)
        else:
            try:
                mtime = os.stat(root / album.cover_source.split(":", 1)[1]).st_mtime
            except OSError:
                mtime = None
            if mtime != album.cover_mtime:
                work.append(album)
    if not work:
        return 0
    files: dict[int, list[str]] = {}
    rows = db.execute(
        select(Track.album_id, Track.file_path)
        .where(Track.album_id.in_([a.id for a in work]), Track.missing_at.is_(None))
        .order_by(Track.album_id, Track.disc_no.nulls_first(), Track.track_no.nulls_last(), Track.file_path)
    )
    for album_id, rel in rows:
        files.setdefault(album_id, []).append(rel)
    changed = 0
    for album in work:
        check_cancel()
        rels = [r for r in files.get(album.id, []) if reachable(r)]
        if not rels:
            continue
        before = album.cover_version
        if album.cover_path is None:
            # only a new cover.jpg can have appeared: changed audio files were already tried
            _cover_from_folder(album, root, (root / rels[0]).parent)
        elif not (
            any(_cover_from_file(album, root / r, r) for r in rels[:3])
            or _cover_from_folder(album, root, (root / rels[0]).parent)
        ):
            # the cover is gone from the files: drop it so the placeholder shows
            remove_covers([album.id])
            album.cover_path, album.cover_source, album.cover_mtime = None, None, None
            album.cover_version += 1
        if album.cover_version != before:
            changed += 1
    return changed


def _walk(
    root: Path, on_error, skip_top: set[str], skip_paths: frozenset[str] = frozenset(), exts=AUDIO_EXTS,
    start: Path | None = None,
):
    """Yields (path, is_symlink) for audio files under root, following symlinked folders and mounts.

    Folder loops (a link pointing at its own parent) are visited once.
    on_error(path, exc) is called for folders that can't be read and for broken links.
    Top-level folders named in skip_top (NFC) are not entered, nor folders in skip_paths
    (absolute, normalized: the audiobook folder when it sits inside the music folder).
    start: walk only this folder under root (a per-folder scan).
    """
    stack = [start or root]
    visited: set[tuple[int, int]] = set()
    while stack:
        check_cancel()  # listing a large share can take a while by itself
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
                    skipped = (directory == root and nfc(entry.name) in skip_top) or (
                        os.path.normpath(entry.path) in skip_paths
                    )
                    if not entry.name.startswith("@") and not skipped:  # @: Synology @eaDir etc.
                        stack.append(Path(entry.path))
                    continue
                if entry.is_symlink() and not os.path.exists(entry.path):
                    on_error(Path(entry.path), FileNotFoundError(2, "broken link"))
                    continue
            except OSError as exc:
                on_error(Path(entry.path), exc)
                continue
            if os.path.splitext(entry.name)[1].lower() in exts:
                yield Path(entry.path), entry.is_symlink()  # from the directory listing: no extra call


def _collect(
    root: Path, existing: dict[str, Track], on_error, skip_top: set[str], skip_paths: frozenset[str] = frozenset(),
    start: Path | None = None,
) -> list[tuple[str, Path, os.stat_result]]:
    """Lists (relative path, path, stat) for each real file. The one stat per file is reused
    for the size/mtime check, which on a NAS share is most of the cost of a rescan.

    A file and symlinks to it are indexed once, preferring the path already in the DB so
    playlists keep pointing at it. Hard links stay separate files (a chart folder may hard-link
    album files), as when files were told apart by their real path.
    """
    by_inode: dict[tuple[int, int], list[tuple[str, Path, os.stat_result, bool]]] = {}
    for path, is_link in _walk(root, on_error, skip_top, skip_paths, start=start):
        rel = os.path.relpath(path, root)
        try:
            rel.encode("utf-8")
        except UnicodeEncodeError:
            on_error(path, ValueError("invalid file name encoding"))
            continue
        try:
            st = os.stat(path)
        except OSError as exc:
            on_error(path, exc)
            continue
        by_inode.setdefault((st.st_dev, st.st_ino), []).append((rel, path, st, is_link))
    files = []
    for candidates in by_inode.values():
        real = [c[:3] for c in candidates if not c[3]]
        if len(real) > 1:
            files.extend(real)  # hard links: one track per path (symlinks to them are dropped)
            continue
        known = [c for c in candidates if c[0] in existing]
        files.append(min(known or candidates, key=lambda c: c[0])[:3])
    return files


def _run(job_id: int) -> None:
    try:
        _scan(job_id)
    finally:
        _lock.release()


def _scan(job_id: int) -> None:
    db = SessionLocal()
    job = db.get(ScanJob, job_id)
    errors: list[str] = []
    pruned_albums: list[int] = []
    reset_albums: list[int] = []  # gone with a folder reset: their covers go even if the scan then fails
    try:
        root = settings.music_dir
        if not root.is_dir():
            raise RuntimeError(f"music_dir_not_found: {root}")
        kinds = folder_kinds(db)
        scope = job.folder  # one top-level folder (NFC), or None for the whole library
        start = None
        if scope is not None:
            # stored names are NFC; on disk the folder may be spelled NFD (made on a Mac)
            start = next((root / e.name for e in os.scandir(root) if e.is_dir() and nfc(e.name) == scope), None)
            if start is None:
                raise RuntimeError(f"folder_not_found: {scope}")
            if job.mode == "reset":
                # forget the folder's songs (and with them their stars, likes, plays and playlist places)
                ids = list(db.scalars(select(Track.id).where(in_folder(scope))))
                for i in range(0, len(ids), 1000):
                    db.execute(delete(Track).where(Track.id.in_(ids[i : i + 1000])))
                reset_albums = prune_orphans(db)
                bump_library(db)
                db.commit()
        cache = _Cache(db)
        query = select(Track).options(defer(Track.tag_json))
        if scope is not None:
            query = query.where(in_folder(scope))
        existing = {t.file_path: t for t in db.scalars(query)}
        reread = job.mode == "rescan"  # read every tag again, even of unchanged files
        unavailable: list[str] = []  # folders we could not read: keep their tracks as they are
        cover_tries: dict[int, int] = {}
        pending = 0  # unchanged files whose row changed (came back, refiled) since the last commit
        batch: list[Pending] = []
        bumped = time.monotonic()

        def commit(changed: bool) -> None:
            """Commits, and now and then lets cached lists see the new songs while a long scan runs."""
            nonlocal bumped
            if changed and time.monotonic() - bumped > 20:
                bump_library(db)
                bumped = time.monotonic()
            db.commit()

        def on_error(path: Path, exc: Exception) -> None:
            # usually PUID/PGID lacking permission, an unmounted share or a broken link
            job.errors += 1
            unavailable.append(os.path.relpath(path, root))
            if len(errors) < 50:
                errors.append(f"cannot read: {path}: {getattr(exc, 'strerror', None) or exc}")

        def file_error(rel: str, exc: Exception) -> None:
            job.errors += 1
            if len(errors) < 50:
                errors.append(f"{rel}: {exc}")

        def store(items: list[Pending]) -> None:
            """Writes read files in one savepoint; if that fails, one by one to find the bad file."""
            nonlocal cache, pending
            try:
                with db.begin_nested():
                    done = _store(db, cache, existing, items, cover_tries)
            except Exception:
                cache = _Cache(db, cache.moves)  # rows made inside the rolled-back savepoint are gone
                done = []
                for item in items:
                    try:
                        with db.begin_nested():
                            done += _store(db, cache, existing, [item], cover_tries)
                    except Exception as exc:  # one bad file must not stop the scan
                        file_error(item[0], exc)
                        cache = _Cache(db, cache.moves)
            for rel, track, is_new in done:
                existing[rel] = track
                if is_new:
                    job.added += 1
                else:
                    job.updated += 1
            commit(bool(done))
            pending = 0

        # mp3 audiobooks in a folder inside the music folder must not turn into songs
        books_dir = settings.books_root
        skip_paths = frozenset([os.path.normpath(books_dir)]) if books_dir else frozenset()
        excluded = {p for p, k in kinds.items() if k == "excluded"}
        files = [] if scope in excluded else _collect(root, existing, on_error, excluded, skip_paths, start)
        if not files and scope not in excluded and any(t.missing_at is None for t in existing.values()):
            # an empty library is almost always an unmounted folder; don't hide everything
            raise RuntimeError(f"library_empty: no audio files found under {start or root}")
        seen = {rel for rel, _, _ in files}

        places: dict[str, Placement] = {}  # placement depends only on the folder: work it out once per folder
        for rel, path, st in files:
            check_cancel()
            job.scanned += 1
            folder = os.path.dirname(rel)
            place = places.get(folder)
            if place is None:
                place = places[folder] = placement(rel, kinds)
            track = existing.get(rel)
            if track and not reread and track.file_size == st.st_size and track.file_mtime == st.st_mtime:
                try:
                    changed = track.missing_at is not None
                    track.missing_at = None
                    if not cache.matches(track, place):
                        # folder kind changed (or first scan after upgrade): refile from stored tags
                        with db.begin_nested():
                            raw = track.tag_json if track.tag_json is not None else _read_tags(path)[0]
                            _classify(cache, track, raw, path, place, cover_tries)
                            db.flush()
                        changed = True
                    if changed:
                        job.updated += 1
                        pending += 1
                except Exception as exc:
                    file_error(rel, exc)
                    cache = _Cache(db, cache.moves)
                if pending >= BATCH:
                    commit(True)
                    pending = 0
                continue
            # new or changed: read it now, write it with the next batch
            try:
                raw, duration = _read_tags(path)
            except Exception as exc:
                file_error(rel, exc)
                continue
            batch.append((rel, path, st, place, raw, duration))
            if len(batch) >= BATCH:
                store(batch)
                batch = []
        if batch:
            store(batch)

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
        changed = bool(job.added or job.updated or job.missing)
        # a scan that stopped early skipped these, so the next one does them even with nothing new
        last = db.scalar(
            select(ScanJob.status)
            .where(ScanJob.id < job_id, ScanJob.folder.is_(None))
            .order_by(ScanJob.id.desc())
            .limit(1)
        )
        if changed or last != "done" or scope is not None:
            _link_chart_duplicates(db)
            pruned_albums = prune_orphans(db, cache.moves)
        covers = _refresh_covers(db, root, reachable, cover_tries)
        banners = _find_banners(db, root)
        from .artist_images import folder_images  # imports scanner helpers

        artists = folder_images(db, root)
        if changed or pruned_albums or covers or banners or artists:
            bump_library(db)
        job.status = "done"
    except ScanCancelled:
        # keep what was read so far; nothing is marked missing or pruned on a partial pass
        job.status = "cancelled"  # pruned_albums stays: a stop during the cover refresh comes after pruning
        if job.added or job.updated:
            bump_library(db)
    except Exception as exc:
        log.exception("scan failed")
        db.rollback()
        pruned_albums = []
        job = db.get(ScanJob, job_id)
        job.status = "failed"
        errors.append(str(exc))
        bump_library(db)  # earlier batches were committed
    db.commit()
    if settings.audiobook_dir is not None and job.status != "cancelled" and job.folder is None:
        from .books import scan_books  # books imports scanner helpers

        try:
            scan_books(db, job, errors)
        except ScanCancelled:
            db.commit()
            job.status = "cancelled"
        except Exception as exc:
            log.exception("audiobook scan failed")
            db.rollback()
            job = db.get(ScanJob, job_id)
            job.errors += 1
            errors.append(f"audiobooks: {exc}")
    try:
        job.finished_at = datetime.now(UTC)
        job.error_summary = "\n".join(errors) or None
        db.commit()
    finally:
        db.close()
    remove_covers(pruned_albums + reset_albums)


def _link_chart_duplicates(db: Session) -> None:
    """The same song in several chart weeks or themes: keep the copy in the newest chart week
    (a theme copy only when no chart has it), point the others at it.

    Lists and search show only tracks without canonical_track_id; each chart still lists its own copy.
    """
    rows = db.execute(
        select(Track.id, Track.title, Track.artist_text, Chart.title, Chart.folder_path, Chart.kind)
        .join(Chart, Chart.id == Track.chart_id)
        .where(Track.missing_at.is_(None))
    ).all()
    groups: dict[tuple[str, str], list] = {}
    for row in rows:
        groups.setdefault((nfc(row[1]).casefold(), nfc(row[2]).casefold()), []).append(row)
    wanted: dict[int, int | None] = {}
    for copies in groups.values():
        newest = max(copies, key=lambda r: (r[5] == "chart", r[3], r[4], r[0]))[0]
        for r in copies:
            wanted[r[0]] = None if r[0] == newest else newest
    current = dict(db.execute(select(Track.id, Track.canonical_track_id).where(Track.canonical_track_id.is_not(None))).all())
    changes = [
        {"id": track_id, "canonical_track_id": target}
        for track_id, target in {**{i: None for i in current}, **wanted}.items()
        if current.get(track_id) != target
    ]
    if changes:
        db.execute(update(Track), changes)


def _find_banners(db: Session, root: Path) -> bool:
    """Notes a banner.jpg (or .png/.webp) in each chart/theme folder. Returns whether one changed."""
    changed = False
    for chart in db.scalars(select(Chart)):
        found = None
        try:
            names = {e.name.casefold(): e.name for e in os.scandir(root / chart.folder_path) if e.is_file()}
        except OSError:
            continue  # unreadable now: keep what we had
        for name in BANNER_NAMES:
            if name in names:
                found = str(Path(chart.folder_path) / names[name])
                break
        if chart.banner_file != found:
            chart.banner_file = found
            changed = True
    return changed


def carry_album_marks(db: Session, moves: dict[int, int]) -> None:
    """Stars, likes and videos of albums about to be pruned move to the album their songs went to.
    Where the user already marked the new album, that mark stays (and the old one goes with the album)."""
    for old, new in moves.items():
        for model in (AlbumRating, AlbumFavorite):
            taken = select(model.user_id).where(model.album_id == new)
            db.execute(update(model).where(model.album_id == old, model.user_id.not_in(taken)).values(album_id=new))
        taken = select(Video.youtube_id).where(Video.album_id == new)
        db.execute(update(Video).where(Video.album_id == old, Video.youtube_id.not_in(taken)).values(album_id=new))


def prune_orphans(db: Session, moves: dict[int, int] | None = None) -> list[int]:
    """Deletes albums, charts, artists and genres no track uses any more. Returns deleted album ids.

    Missing tracks still count as users, so they get their album back when they reappear.
    """
    albums = list(db.scalars(select(Album.id).where(~exists().where(Track.album_id == Album.id))))
    if albums and moves:
        carry_album_marks(db, {old: new for old, new in moves.items() if old in set(albums) and new not in albums})
    if albums:
        db.execute(delete(Album).where(Album.id.in_(albums)))
    db.execute(delete(Chart).where(~exists().where(Track.chart_id == Chart.id)))
    gone_artists = db.scalars(
        delete(Artist)
        .where(~exists().where(Track.artist_id == Artist.id), ~exists().where(Album.album_artist_id == Artist.id))
        .returning(Artist.id)
    ).all()
    for artist_id in gone_artists:  # their photos (artist_images.SIZES)
        for size in ("thumb", "large"):
            (settings.cover_dir / f"artist_{artist_id}_{size}.jpg").unlink(missing_ok=True)
    db.execute(delete(Genre).where(~exists().where(TrackGenre.genre_id == Genre.id)))
    return albums


def remove_covers(album_ids: list[int]) -> None:
    for album_id in album_ids:
        for size in COVER_SIZES:
            cover_file(album_id, size).unlink(missing_ok=True)


def bump_library(db: Session) -> None:
    """Marks the library as changed: cached lists and ETags keyed on the old version go stale."""
    db.execute(update(LibraryState).values(version=LibraryState.version + 1, updated_at=func.now()))


def in_folder(folder: str):
    """Tracks under one top-level folder, whatever Unicode form the path is stored in."""
    top = func.split_part(Track.file_path, "/", 1)
    return func.normalize(top, text("NFC")) == folder


def start_scan(db: Session, folder: str | None = None, mode: str = "scan") -> ScanJob | None:
    """Starts a background scan of the library, or of one top-level folder (scan: new and changed
    files; rescan: every file's tags again, ids kept; reset: the folder's songs are forgotten and
    read again as new). Returns None when one is already running."""
    if not _lock.acquire(blocking=False):
        return None
    _cancel.clear()
    job = ScanJob(status="running", folder=folder, mode=mode)
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
