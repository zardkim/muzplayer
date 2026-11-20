"""Library scanner: reads tags from MUSIC_DIR into the DB. Never modifies music files."""

import io
import logging
import os
import re
import threading
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3
from mutagen.easymp4 import EasyMP4Tags
from PIL import Image
from sqlalchemy import delete, exists, func, insert, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased, defer

from . import artist_links, search_index
from .lyrics import lyrics_in_tags
from .config import settings
from .library_paths import chosen_lrc, extract_top, library_path, library_rel
from .db import SessionLocal
from .models import (
    Album, AlbumFavorite, AlbumRating, Artist, Chart, ExtractJob, Favorite, FetchedLyrics, Genre, LibraryFolder,
    LibraryState, NameAlias, PlayCount, PlayHistory, PlaylistTrack, ScanIssue, ScanJob, Track, TrackArtist, TrackGenre,
    TrackRating, Video,
)

log = logging.getLogger(__name__)

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".mp4", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wma", ".ape", ".aif", ".aiff"}
FOLDER_COVERS = ("cover", "folder", "front", "album")
COVER_SIZES = {"thumb": 300, "large": 1000}
BATCH = 200
ISSUES_KEPT = 5000  # scan problems kept for the admin's list

FOLDER_KINDS = ("album", "compilation", "chart", "theme", "excluded", "extracted")  # extracted: extract.py's folder
COLLECTION_KINDS = ("chart", "theme")  # folders of collections: each folder with audio files is one
UNOFFICIAL_DIRS = {"비정규", "unofficial"}  # compared casefolded, at any depth
VARIOUS_ARTISTS = "Various Artists"
# "001 Artist - Title.mp3": a short number then a separator; "2002.mp3" is a title, not a rank
RANK_PREFIX = re.compile(r"^\s*(\d{1,3})(?:[\s._\-)\]]+)")
# "1-03 Artist - Title.mp3": disc 1, track 3 (no rank; the numbers repeat from disc to disc)
DISC_TRACK = re.compile(r"^\s*(\d{1,2})[-.](\d{1,3})(?:[\s._\-)\]]+)")
DISC_DIR = re.compile(r"^(?:cd|disc|disk)\s*[-_.]?\s*(\d+)$", re.IGNORECASE)
BANNER_NAMES = ("banner.jpg", "banner.jpeg", "banner.png", "banner.webp")

# Folders a NAS, Windows or a Mac makes for itself: never music, never shown. By prefix: . (hidden,
# .dav, .Trash-1000) and @ (Synology @eaDir, @tmp); the rest by name (casefolded), so a real album
# folder such as "#1 Hits" or "$uicideboy$" stays.
SYSTEM_DIR_PREFIXES = (".", "@")
SYSTEM_DIR_NAMES = {
    "#recycle", "#snapshot", "$recycle.bin", "recycler", "system volume information", "lost+found",
    "recycle bin", "trash", "trashes", "휴지통", "eadir", "easydir", "network trash folder", "temporary items",
}


def system_dir(name: str) -> bool:
    """A recycle bin, thumbnail cache or other folder the system made (see SYSTEM_DIR_NAMES)."""
    return name.startswith(SYSTEM_DIR_PREFIXES) or nfc(name).casefold() in SYSTEM_DIR_NAMES


_lock = threading.Lock()
_cancel = threading.Event()  # set by an admin's "stop scan"; checked between files


class ScanCancelled(Exception):
    pass


def check_cancel() -> None:
    if _cancel.is_set():
        raise ScanCancelled


def scan_running() -> bool:
    return _lock.locked()


def scan_lock() -> threading.Lock:
    """Held by a scan; merge.py takes it too, so a scan never runs on ids being merged away."""
    return _lock


def cancel_scan() -> bool:
    """Asks the running scan to stop after the current file. False when none is running."""
    if not _lock.locked():
        return False
    _cancel.set()
    return True

# Tags easy mode leaves out but the album kind needs: ID3 TXXX:RELEASETYPE (Picard, Mp3tag) and the
# MP4 compilation flag (iTunes "part of a compilation").
EasyID3.RegisterTXXXKey("releasetype", "RELEASETYPE")
# ReplayGain as foobar2000, Mp3tag and most taggers write it in MP3s (easy mode reads only RVA2)
for _key in ("replaygain_track_gain", "replaygain_track_peak", "replaygain_album_gain", "replaygain_album_peak"):
    EasyID3.RegisterTXXXKey(_key, _key.upper())


def _mp4_compilation(tags, key):
    return ["1"] if tags.get("cpil") else []


def _mp4_set_compilation(tags, key, value):
    tags["cpil"] = bool(value and value[0] not in ("0", ""))


def _mp4_del_compilation(tags, key):
    tags.pop("cpil", None)


EasyMP4Tags.RegisterKey("compilation", _mp4_compilation, _mp4_set_compilation, _mp4_del_compilation)

# Album kind from tags, when the folder says nothing (folder kinds and 비정규 folders win; a
# soundtrack in a compilation folder is still a soundtrack).
# Soundtrack: a release type of soundtrack, or "OST" / "Original Soundtrack" / "사운드트랙" in the
# album name. Compilation: the compilation flag (ID3 TCMP, Vorbis COMPILATION, MP4 cpil), a release type of
# compilation, or an album artist like "Various Artists".
# 비정규 (singles, EPs, mini albums): a release type of single/ep, or the album name saying so
# ("Love - Single", "Love [EP]", "1st 미니앨범"). Only album-level tags, so one album's songs agree.
VA_NAMES = {"various artists", "various", "va", "v.a.", "v/a", "여러 아티스트", "여러 가수", "베리어스 아티스트", "옴니버스"}
RELEASE_TYPE_KEYS = ("releasetype", "release type", "musicbrainz_albumtype", "musicbrainz album type")
SOUNDTRACK = re.compile(r"(?<![a-z])o\.?s\.?t(?![a-z])|original\s+(?:motion\s+picture\s+)?soundtrack|사운드\s*트랙", re.IGNORECASE)
SHORT_RELEASE = re.compile(
    r"(?:[\[(]\s*(?:digital\s+)?(?:single|ep|mini[\s-]?album|싱글|디지털\s*싱글|미니\s*앨범|미니)\s*[\])]"
    r"|\s-\s*(?:single|ep)$|\s(?:single|ep)$|미니\s*앨범|디지털\s*싱글|\d\s*(?:st|nd|rd|th)\s+mini\b)",
    re.IGNORECASE,
)


def tag_kind(raw: dict[str, list[str]]) -> str:
    """soundtrack | compilation | unofficial | '' (nothing in the tags)."""
    types = {
        t for key in RELEASE_TYPE_KEYS for v in raw.get(key, []) for t in re.split(r"[;,/\s]+", v.casefold()) if t
    }
    if "soundtrack" in types or SOUNDTRACK.search(_first(raw, "album")):
        return "soundtrack"
    if any(v.strip().casefold() in ("1", "true", "yes") for v in raw.get("compilation", [])[:1]):
        return "compilation"
    if "compilation" in types:
        return "compilation"
    if nfc(_first(raw, "albumartist")).casefold() in VA_NAMES:
        return "compilation"
    if types & {"single", "ep"} and "album" not in types:
        return "unofficial"
    if SHORT_RELEASE.search(_first(raw, "album")):
        return "unofficial"
    return ""


def album_kind(place: "Placement", track: Track) -> str:
    """The kind of album a track is filed under: the folder's, else what its tags say."""
    if place.kind == "compilation" and track.tag_kind == "soundtrack":
        return "soundtrack"
    if place.kind != "album":
        return place.kind
    return track.tag_kind or "album"


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


LOSSLESS_EXTS = {".flac", ".wav", ".aif", ".aiff", ".ape", ".wv"}  # and ALAC in .m4a (by codec)


def audio_info(audio, path: Path) -> dict:
    """Length and quality from the file header: sample rate, bit depth (lossless files only:
    AAC reports 16 bits too) and bitrate in kbps. Unknown values are 0, so they aren't read again."""
    info = audio.info
    lossless = path.suffix.lower() in LOSSLESS_EXTS or getattr(info, "codec", "") == "alac"
    rate = getattr(info, "sample_rate", 0) or 0
    bits = getattr(info, "bits_per_sample", 0) or 0
    bitrate = getattr(info, "bitrate", 0) or 0
    return {
        "duration": getattr(info, "length", None),
        "sample_rate": int(rate),
        "bit_depth": int(bits) if lossless else 0,
        "bitrate": int(bitrate / 1000),
    }


DAMAGED = "_damaged"  # in tag_json: a file only ffmpeg could read (_read_damaged); streamed converted


def _read_damaged(path: Path, exc: Exception) -> tuple[dict[str, list[str]], dict]:
    """An MP3 the tag library gave up on ("can't sync to MPEG frame": usually junk or a broken
    picture before the audio). Its tags from the ID3 block, its length and quality from ffmpeg
    decoding it. Raises the original error when ffmpeg can't decode it either."""
    from .transcode import probe  # transcode doesn't need the scanner; only this path needs it

    if path.suffix.lower() != ".mp3":
        raise exc
    info = probe(path)
    if info is None:
        raise exc
    raw: dict[str, list[str]] = {}
    try:
        tags = EasyID3(path)
        for key in tags.keys():
            values = _text_values(tags[key])
            if values:
                raw[str(key).lower()] = values
    except Exception:  # noqa: BLE001 - no readable tags: the file name stands in, as for untagged files
        pass
    raw[DAMAGED] = ["1"]
    log.info("read with ffmpeg (damaged MP3): %s", path)
    return raw, info


def _read_info(path: Path) -> dict:
    try:
        audio = mutagen.File(path)
    except mutagen.MutagenError as exc:
        return _read_damaged(path, exc)[1]
    if audio is None:
        raise ValueError("unsupported file")
    return audio_info(audio, path)


def _easy_get(tags: ID3, key: str) -> list[str]:
    try:
        return EasyID3.Get[key](tags, key)
    except (KeyError, ValueError):
        return []


def _read_tags(path: Path) -> tuple[dict[str, list[str]], dict]:
    try:
        audio = mutagen.File(path, easy=True)
    except mutagen.MutagenError as exc:
        return _read_damaged(path, exc)
    if audio is None:
        raise ValueError("unsupported file")
    raw: dict[str, list[str]] = {}
    tags = audio.tags
    if isinstance(tags, ID3) and not isinstance(tags, EasyID3):
        # WAV and AIFF keep ID3 tags that easy mode leaves raw (TIT2, ...): name them as EasyID3 does
        tags = {k: v for k in EasyID3.Get if (v := _easy_get(tags, k))}
    for key, value in (tags or {}).items():
        values = _text_values(value)
        if values:
            raw[str(key).lower()] = values
    return raw, audio_info(audio, path)


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


def full_date(text: str | None) -> date | None:
    """A whole release date (2011-11-28, 2011.11.28), or None for just a year or a bad date."""
    m = re.match(r"\s*(\d{4})[-./](\d{2})[-./](\d{2})", text or "")
    try:
        return date(int(m[1]), int(m[2]), int(m[3])) if m else None
    except ValueError:
        return None


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


def _cover_from_folder(album: Album, directory: Path) -> bool:
    """cover.jpg (folder.jpg, ...) next to the audio files."""
    image = _folder_cover(directory)
    if image is None:
        return False
    try:
        data, mtime = image.read_bytes(), image.stat().st_mtime
    except OSError:
        return False
    return _set_album_cover(album, data, f"folder:{library_rel(image)}", mtime)


def folder_kinds(db: Session) -> dict[str, str]:
    """Top-level folder name (NFC) -> kind. Folders not listed are "album"."""
    return {f.path: f.kind for f in db.scalars(select(LibraryFolder))}


@dataclass(frozen=True)
class Placement:
    """Where a file belongs, decided by its path alone."""

    kind: str  # album kind: album | unofficial | compilation | extracted | chart (also for themes)
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
    if folder_kind == "extracted":  # audio taken out of music videos (extract.py)
        return Placement("extracted")
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
        # merged duplicates (merge.py): a name as tagged -> the name it is filed under
        self.aliases: dict[str, dict[str, str]] = {"artist": {}, "genre": {}}
        for a in db.scalars(select(NameAlias)):
            self.aliases.setdefault(a.kind, {})[a.name] = a.target

    def artist_name(self, name: str) -> str:
        return self.aliases["artist"].get(name, name)

    def matches(self, track: Track, place: Placement) -> bool:
        """Whether the track is already filed the way its path says."""
        return (
            self.album_kinds.get(track.album_id) == album_kind(place, track)
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
        name = self.artist_name(name)
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
        name = self.aliases["genre"].get(name, name)
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
    info: dict,
    path: Path,
    place: Placement,
    cover_tries: dict[int, int],
) -> None:
    artists = [cache.artist_name(a[:500]) for a in _pick(raw, "artist")]
    track.artist_text = " / ".join(artists)[:1000]
    track.artist_id = cache.artist((artists or [""])[0])
    track.track_no = _number(_first(raw, "tracknumber"))
    track.disc_no = _number(_first(raw, "discnumber"))
    if track.track_no is None or track.disc_no is None:  # untagged: from the name, "1-03 …", "03 …", ".../CD2/…"
        stem, folder = nfc(path.stem), nfc(path.parent.name)
        numbers = DISC_TRACK.match(stem)
        rank = RANK_PREFIX.match(stem)
        if track.track_no is None:
            track.track_no = int(numbers.group(2)) if numbers else int(rank.group(1)) if rank else None
        if track.disc_no is None and (numbers or (m := DISC_DIR.match(folder))):
            track.disc_no = int(numbers.group(1)) if numbers else int(m.group(1))
    _set_info(track, info)
    track.tag_json = {k: v[:5] for k, v in raw.items() if len(k) < 64}
    track.tag_kind = tag_kind(raw)
    track.lrc_tag = lyrics_in_tags(path)
    for key, value in replaygain(raw).items():
        setattr(track, key, value)
    _classify(cache, track, raw, path, place, cover_tries)


def replaygain(raw: dict[str, list[str]]) -> dict[str, float | None]:
    """ReplayGain values from the tags ("-7.53 dB", "0.988"); keys as on Track, None when missing."""
    out: dict[str, float | None] = {}
    for scope in ("track", "album"):
        for part in ("gain", "peak"):
            text = (raw.get(f"replaygain_{scope}_{part}") or [""])[0]
            m = re.match(r"\s*([-+]?\d+(?:[.,]\d+)?)", text)
            out[f"rg_{scope}_{part}"] = float(m[1].replace(",", ".")) if m else None
    return out


def _set_info(track: Track, info: dict) -> None:
    track.duration = info["duration"]
    track.sample_rate, track.bit_depth, track.bitrate = info["sample_rate"], info["bit_depth"], info["bitrate"]


# one new or changed file, read but not yet written: (rel, path, stat, placement, tags, audio info)
Pending = tuple[str, Path, os.stat_result, Placement, dict[str, list[str]], dict]


def _store(
    db: Session, cache: _Cache, existing: dict[str, Track], items: list[Pending], cover_tries: dict[int, int]
) -> list[tuple[str, Track, bool]]:
    """Writes a batch of read files with a few statements instead of several per file.
    Returns (rel, track, is_new) for each; existing is left alone until the caller commits."""
    done: list[tuple[str, Track, bool]] = []
    genres: list[tuple[Track, set[int]]] = []
    for rel, path, st, place, raw, info in items:
        track = existing.get(rel)
        is_new = track is None
        if is_new:
            track = Track(file_path=rel, title="", file_size=st.st_size, file_mtime=st.st_mtime,
                          format=path.suffix.lower().lstrip("."))
            db.add(track)
        track.file_size, track.file_mtime, track.missing_at = st.st_size, st.st_mtime, None
        _apply_tags(cache, track, raw, info, path, place, cover_tries)
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
    # "001 Artist - Title" -> "Artist - Title", "1-03 Title" -> "Title" (the numbers are the rank, or disc and track)
    stem = RANK_PREFIX.sub("", DISC_TRACK.sub("", stem)) or stem
    track.title = (_first(raw, "title") or stem)[:1000]
    if track.tag_kind is None:
        track.tag_kind = tag_kind(raw)
    kind = album_kind(place, track)
    folder = rel.parent.parent if DISC_DIR.match(nfc(rel.parent.name)) and len(rel.parts) > 2 else rel.parent  # .../Album/CD2/x.mp3
    album_title = _first(raw, "album") or nfc(folder.name) or ""
    album_artist = _first(raw, "albumartist") or (
        VARIOUS_ARTISTS if kind in ("compilation", "soundtrack") else (_pick(raw, "artist") or [""])[0]
    )
    album = cache.album(kind, album_title[:500], cache.artist(album_artist[:500]), _year(_first(raw, "date")))
    if album.release_date is None:
        album.release_date = full_date(_first(raw, "date")) or full_date(raw.get("originaldate", [""])[0])
    if track.album_id is not None and track.album_id != album.id:
        cache.moves.setdefault(track.album_id, album.id)
    track.album_id = album.id
    track.search_text = search_index.index_text(track.title, track.artist_text, album.title)
    if place.chart_folder is not None:
        track.chart_id = cache.chart(place.chart_folder, place.chart_source, place.chart_kind)
        rank = RANK_PREFIX.match(rel.stem)
        if DISC_TRACK.match(rel.stem):
            track.chart_position = None
        else:
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
    if _cover_from_file(album, path, rel) or _cover_from_folder(album, path.parent):
        cover_tries[album.id] = 3


def _refresh_covers(db: Session, reachable, cover_tries: dict[int, int]) -> int:
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
                mtime = os.stat(library_path(album.cover_source.split(":", 1)[1])).st_mtime
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
            _cover_from_folder(album, library_path(rels[0]).parent)
        elif not (
            any(_cover_from_file(album, library_path(r), r) for r in rels[:3])
            or _cover_from_folder(album, library_path(rels[0]).parent)
        ):
            # the cover is gone from the files: drop it so the placeholder shows
            remove_covers([album.id])
            album.cover_path, album.cover_source, album.cover_mtime = None, None, None
            album.cover_version += 1
        if album.cover_version != before:
            changed += 1
    return changed


def lrc_key(path: str) -> str:
    """Song.mp3 and Song.lrc (any case) give the same key."""
    return os.path.splitext(path)[0].casefold()


def _walk(
    root: Path, on_error, skip_top: set[str], skip_paths: frozenset[str] = frozenset(), exts=AUDIO_EXTS,
    start: Path | None = None, lrc: set[str] | None = None,
):
    """Yields (path, is_symlink) for audio files under root, following symlinked folders and mounts.

    Folder loops (a link pointing at its own parent) are visited once.
    on_error(path, exc) is called for folders that can't be read and for broken links.
    Top-level folders named in skip_top (NFC) are not entered, nor folders in skip_paths
    (absolute, normalized: the audiobook folder when it sits inside the music folder).
    start: walk only this folder under root (a per-folder scan).
    lrc: filled with lrc_key() of the .lrc files seen (lyrics next to songs).
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
                    if not system_dir(entry.name) and not skipped:  # recycle bins, @eaDir...
                        stack.append(Path(entry.path))
                    continue
                if entry.is_symlink() and not os.path.exists(entry.path):
                    on_error(Path(entry.path), FileNotFoundError(2, "broken link"))
                    continue
            except OSError as exc:
                on_error(Path(entry.path), exc)
                continue
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in exts:
                yield Path(entry.path), entry.is_symlink()
            elif ext == ".lrc" and lrc is not None:
                lrc.add(lrc_key(entry.path))  # from the directory listing: no extra call


def _collect(
    root: Path, existing: dict[str, Track], on_error, skip_top: set[str], skip_paths: frozenset[str] = frozenset(),
    start: Path | None = None, lrc: set[str] | None = None,
) -> list[tuple[str, Path, os.stat_result]]:
    """Lists (relative path, path, stat) for each real file. The one stat per file is reused
    for the size/mtime check, which on a NAS share is most of the cost of a rescan.

    A file and symlinks to it are indexed once, preferring the path already in the DB so
    playlists keep pointing at it. Hard links stay separate files (a chart folder may hard-link
    album files), as when files were told apart by their real path.
    """
    by_inode: dict[tuple[int, int], list[tuple[str, Path, os.stat_result, bool]]] = {}
    for path, is_link in _walk(root, on_error, skip_top, skip_paths, start=start, lrc=lrc):
        rel = library_rel(path)  # (the extraction folder's files under its own top-level name)
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


def _move_keys(rel: str, size: int, mtime: float) -> tuple[tuple, tuple]:
    """What tells a moved file: its size with its name (NFC, any case), or its size with its mtime
    (renamed too; a move on the same share keeps it)."""
    return (size, nfc(os.path.basename(rel)).casefold()), (size, mtime)


def _take_over(db: Session, old: int, fresh: int) -> None:
    """Moves what users did with a song's duplicate (made by an earlier scan that did not see the move)
    onto the song; where both have one (a like, a star), the song's own stays. The duplicate is deleted after."""
    for model in (Favorite, TrackRating):
        taken = select(model.user_id).where(model.track_id == old)
        db.execute(update(model).where(model.track_id == fresh, model.user_id.not_in(taken)).values(track_id=old))
    both = aliased(PlayCount)
    db.execute(
        update(PlayCount)
        .where(PlayCount.track_id == old, both.track_id == fresh, both.user_id == PlayCount.user_id)
        .values(plays=PlayCount.plays + both.plays, last_played_at=func.greatest(PlayCount.last_played_at, both.last_played_at))
    )
    taken = select(PlayCount.user_id).where(PlayCount.track_id == old)
    db.execute(update(PlayCount).where(PlayCount.track_id == fresh, PlayCount.user_id.not_in(taken)).values(track_id=old))
    for model in (PlaylistTrack, PlayHistory, ExtractJob):
        db.execute(update(model).where(model.track_id == fresh).values(track_id=old))
    taken = select(Video.youtube_id).where(Video.track_id == old, Video.youtube_id.is_not(None))
    db.execute(
        update(Video)
        .where(Video.track_id == fresh, or_(Video.youtube_id.is_(None), Video.youtube_id.not_in(taken)))
        .values(track_id=old)
    )
    if not db.scalar(select(exists().where(FetchedLyrics.track_id == old))):
        db.execute(update(FetchedLyrics).where(FetchedLyrics.track_id == fresh).values(track_id=old))
    db.execute(delete(Track).where(Track.id == fresh))


def _follow_moves(
    db: Session, existing: dict[str, Track], files: list[tuple[str, Path, os.stat_result]], seen: set[str],
    reachable, scope: str | None,
) -> int:
    """Songs whose file is now somewhere else (a folder moved or renamed: album/아이유 -> album/artists/아이유)
    keep their row, so likes, stars, plays and playlists stay with them: the row takes the new path.

    A song gone from its path pairs with a new file of the same size and name (or size and mtime),
    only one to one: a chart folder's copies of album files look alike and are left as they are.
    Also mends what an earlier scan made of a move: the song marked missing and a duplicate added
    in its new place (the duplicate's likes and plays go to the song, then it goes).
    A per-folder scan also looks outside its folder: a folder moved from another top-level one.
    Returns how many songs moved; existing is keyed by the new paths after.
    """
    lost = {p: t for p, t in existing.items() if p not in seen and reachable(p)}
    new = [(rel, st, None) for rel, _, st in files if rel not in existing]
    # duplicates made after their song went missing (with the paths kept so far: an earlier scan's)
    gone = [t.missing_at for t in lost.values() if t.missing_at is not None]
    if gone:
        since = min(gone) - timedelta(hours=12)
        new += [
            (rel, st, existing[rel]) for rel, _, st in files
            if rel in existing and existing[rel].created_at is not None and existing[rel].created_at >= since
        ]
    if not new:
        return 0
    if scope is not None:
        # from another top-level folder: missing already, or its file is no longer there
        sizes = list({st.st_size for _, st, _ in new})
        for i in range(0, len(sizes), 1000):
            for t in db.scalars(
                select(Track).options(defer(Track.tag_json))
                .where(~in_folder(scope), Track.file_size.in_(sizes[i : i + 1000]))
            ):
                if t.missing_at is not None or not os.path.exists(library_path(t.file_path)):
                    lost[t.file_path] = t
    if not lost:
        return 0
    lost_by: dict[tuple, list[Track]] = {}
    for t in lost.values():
        for key in _move_keys(t.file_path, t.file_size, t.file_mtime):
            lost_by.setdefault(key, []).append(t)
    new_by: dict[tuple, int] = {}
    for rel, st, _ in new:
        for key in _move_keys(rel, st.st_size, st.st_mtime):
            new_by[key] = new_by.get(key, 0) + 1
    pairs: list[tuple[Track, str, Track | None]] = []
    taken: set[int] = set()
    for rel, st, fresh in new:
        for key in _move_keys(rel, st.st_size, st.st_mtime):
            found = lost_by.get(key, [])
            if len(found) != 1 or new_by[key] != 1 or found[0].id in taken:
                continue
            old = found[0]
            if fresh is not None and (
                old.missing_at is None or fresh.created_at <= old.created_at or fresh.created_at < old.missing_at - timedelta(hours=12)
            ):
                continue  # a duplicate only of a song already missing, made by the scan that found it gone
            taken.add(old.id)
            pairs.append((old, rel, fresh))
            break
    for old, rel, fresh in pairs:
        if fresh is not None:
            _take_over(db, old.id, fresh.id)
    db.flush()  # the duplicates' paths are free now
    for old, rel, fresh in pairs:
        if existing.get(old.file_path) is old:
            del existing[old.file_path]
        db.execute(update(ExtractJob).where(ExtractJob.file_path == old.file_path).values(file_path=rel))
        # the lyrics an admin chose are kept by the song's path
        src, dst = chosen_lrc(old.file_path), chosen_lrc(rel)
        if src is not None and dst is not None and src.is_file():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, dst)
            except OSError as exc:
                log.warning("moving chosen lyrics %s: %s", src, exc)
        old.file_path = rel
        existing[rel] = old
    db.flush()
    return len(pairs)


def _unite_folder_albums(db: Session, cache: _Cache, scope: str | None) -> int:
    """One folder, one album: songs in the same folder (CD1 / CD2 merged) under the same album title are
    one album, whatever their artist tags say. Without an album artist tag a compilation's songs were each
    filed under their own artist, one album per singer.

    The artist most of them are filed under, when that is more than half; else Various Artists, as a
    compilation. The songs' tag_kind is set to the album's kind, so later scans leave them there (a song
    read again is filed by its tags first, then united again here). Returns how many songs moved.
    """
    query = (
        select(Track.id, Track.file_path, Track.album_id, Album.kind, Album.title, Album.album_artist_id, Album.year)
        .join(Album, Album.id == Track.album_id)
        .where(Track.missing_at.is_(None), Track.chart_id.is_(None), Album.kind.not_in(("chart", "extracted")))
    )
    if scope is not None:
        query = query.where(in_folder(scope))
    groups: dict[tuple[str, str], list] = {}
    for row in db.execute(query):
        rel = Path(row.file_path)
        folder = rel.parent.parent if DISC_DIR.match(nfc(rel.parent.name)) and len(rel.parts) > 2 else rel.parent
        groups.setdefault((str(folder), nfc(row.title).casefold()), []).append(row)
    moved = 0
    for rows in groups.values():
        if len({r.album_id for r in rows}) < 2:
            continue
        artist, n = Counter(r.album_artist_id for r in rows).most_common(1)[0]
        kinds = {r.kind for r in rows}
        if n * 2 > len(rows) and artist is not None:
            kind = next((k for k in ("soundtrack", "compilation") if k in kinds), Counter(r.kind for r in rows).most_common(1)[0][0])
        else:
            artist = cache.artist(VARIOUS_ARTISTS)
            kind = "soundtrack" if "soundtrack" in kinds else "compilation"
        title = Counter(r.title for r in rows).most_common(1)[0][0]
        years = [r.year for r in rows if r.year]
        album = cache.album(kind, title, artist, min(years) if years else None)
        ids = [r.id for r in rows if r.album_id != album.id]
        for r in rows:
            if r.album_id != album.id:
                cache.moves.setdefault(r.album_id, album.id)  # its stars, likes and videos follow
        if ids:
            db.execute(update(Track).where(Track.id.in_(ids)).values(album_id=album.id))
            moved += len(ids)
        db.execute(
            update(Track).where(Track.id.in_([r.id for r in rows]))
            .values(tag_kind=kind if kind in ("compilation", "soundtrack", "unofficial") else "")
        )
    return moved


def _fill_tag_kinds(db: Session, scope: str | None) -> None:
    """Works out tag_kind from the stored tags where it is missing (songs scanned before it existed),
    a chunk at a time; the scan then refiles the songs whose album kind changed."""
    last = 0
    while True:
        check_cancel()
        query = select(Track.id, Track.tag_json).where(Track.tag_kind.is_(None), Track.tag_json.is_not(None), Track.id > last)
        if scope is not None:
            query = query.where(in_folder(scope))
        rows = db.execute(query.order_by(Track.id).limit(2000)).all()
        if not rows:
            return
        db.execute(
            update(Track),
            [{"id": i, "tag_kind": tag_kind(raw or {})} for i, raw in rows],
        )
        db.commit()
        last = rows[-1][0]


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
        # one top-level folder, or a folder inside one (an album's or chart's metadata refreshed; NFC),
        # or None for the whole library
        scope = job.folder
        scope_top = scope.split("/", 1)[0] if scope is not None else None
        inner = scope.split("/")[1:] if scope is not None else []  # the folders under the top-level one
        start = None
        top = extract_top()  # the extraction folder beside the music folder, listed as one of its folders
        if scope is not None and scope_top == top:
            start = _find_dir(settings.extract_dir, inner) if settings.extract_dir.is_dir() else None
            if start is None:
                raise RuntimeError(f"folder_not_found: {scope}")
        elif scope is not None:
            # stored names are NFC; on disk the folder may be spelled NFD (made on a Mac)
            start = _find_dir(root, scope.split("/"))
            if start is None:
                raise RuntimeError(f"folder_not_found: {scope}")
            if job.mode == "reset" and not inner:
                # forget the folder's songs (and with them their stars, likes, plays and playlist places)
                ids = list(db.scalars(select(Track.id).where(in_folder(scope))))
                for i in range(0, len(ids), 1000):
                    db.execute(delete(Track).where(Track.id.in_(ids[i : i + 1000])))
                reset_albums = prune_orphans(db)
                bump_library(db)
                db.commit()
        _fill_tag_kinds(db, scope)
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

        # this scan's problems replace the earlier ones of what it covers (admin → library), and a song
        # it can read again is no longer marked
        db.execute(delete(ScanIssue).where(*([ScanIssue.path.startswith(scope + "/")] if scope is not None else [])))
        db.execute(update(Track).where(Track.scan_error.is_not(None), *([in_folder(scope)] if scope is not None else []))
                   .values(scan_error=None))
        noted = 0

        def note(rel: str, message: str) -> None:
            """Keeps a problem for the admin's list (the first few thousand), and marks the song when there is one."""
            nonlocal noted
            track = existing.get(rel)
            if track is not None:
                track.scan_error = message[:500]
            if noted >= ISSUES_KEPT:
                return
            noted += 1
            db.execute(pg_insert(ScanIssue).values(path=rel, message=message[:1000])
                       .on_conflict_do_update(index_elements=["path"], set_={"message": message[:1000], "at": func.now()}))

        def on_error(path: Path, exc: Exception) -> None:
            # usually PUID/PGID lacking permission, an unmounted share or a broken link
            job.errors += 1
            rel = library_rel(path)
            unavailable.append(rel)
            message = f"cannot read: {getattr(exc, 'strerror', None) or exc}"
            note(rel, message)
            if len(errors) < 50:
                errors.append(f"cannot read: {path}: {getattr(exc, 'strerror', None) or exc}")

        def file_error(rel: str, exc: Exception) -> None:
            job.errors += 1
            note(rel, str(exc) or type(exc).__name__)
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
                track.lrc_file = lrc_key(str(library_path(rel))) in lrc_files
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
        lrc_files: set[str] = set()
        if scope_top in excluded:
            files = []
        elif start is not None and scope_top == top:
            files = _collect(settings.extract_dir, existing, on_error, set(), skip_paths, start, lrc_files)
        else:
            # a folder of the music library named like the extraction folder is left out (the extraction folder is that name)
            files = _collect(root, existing, on_error, excluded | ({top} if top else set()), skip_paths, start, lrc_files)
            if scope is None and top and top not in excluded and settings.extract_dir.is_dir():
                files += _collect(settings.extract_dir, existing, on_error, set(), skip_paths, None, lrc_files)
        if not files and not inner and scope_top not in excluded and any(t.missing_at is None for t in existing.values()):
            # an empty library is almost always an unmounted folder; don't hide everything
            raise RuntimeError(f"library_empty: no audio files found under {start or root}")
        seen = {rel for rel, _, _ in files}

        def reachable(rel: str) -> bool:
            return not any(u == "." or rel == u or rel.startswith(u + os.sep) for u in unavailable)

        if job.mode != "reset":
            job.moved = _follow_moves(db, existing, files, seen, reachable, scope)
            commit(bool(job.moved))

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
                    if track.sample_rate is None:
                        # scanned before quality was kept: read just the header, once
                        try:
                            _set_info(track, _read_info(path))
                        except Exception:  # unreadable header: don't try on every scan
                            track.sample_rate = track.bit_depth = track.bitrate = 0
                        changed = True
                    # lyrics: a .lrc added or removed next to it; the tags looked at once (scanned before this was kept)
                    lyrics = False
                    has_file = lrc_key(str(path)) in lrc_files
                    if track.lrc_file != has_file:
                        track.lrc_file, lyrics = has_file, True
                    if track.lrc_tag is None:
                        track.lrc_tag, lyrics = lyrics_in_tags(path), True
                    if changed:
                        job.updated += 1
                    if changed or lyrics:
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
                raw, info = _read_tags(path)
            except Exception as exc:
                file_error(rel, exc)
                continue
            batch.append((rel, path, st, place, raw, info))
            if len(batch) >= BATCH:
                store(batch)
                batch = []
        if batch:
            store(batch)

        now = datetime.now(UTC)
        gone = [
            t.id
            for path_key, t in existing.items()
            if path_key not in seen and t.missing_at is None and reachable(path_key)
        ]
        for i in range(0, len(gone), 1000):
            db.execute(update(Track).where(Track.id.in_(gone[i : i + 1000])).values(missing_at=now))
        job.missing = len(gone)
        changed = bool(job.added or job.updated or job.missing or job.moved)
        # a scan that stopped early skipped these, so the next one does them even with nothing new
        last = db.scalar(
            select(ScanJob.status)
            .where(ScanJob.id < job_id, ScanJob.folder.is_(None))
            .order_by(ScanJob.id.desc())
            .limit(1)
        )
        relinks = artist_links.outdated(db)  # an update changed how songs are linked to their artists
        if relinks:
            from . import bugs_artists

            bugs_artists.drop_group_names(db)  # (LINKS_VERSION 2)
        united = _unite_folder_albums(db, cache, scope)
        job.updated += united
        changed = changed or bool(united)
        if changed or last != "done" or scope is not None or relinks:
            _link_chart_duplicates(db)
            artist_links.relink(db)  # every song's artists (feat., collaborations), before pruning the unused
            pruned_albums = prune_orphans(db, cache.moves)
            update_album_quality(db)
        covers = _refresh_covers(db, reachable, cover_tries)
        banners = _find_banners(db, root)
        from .artist_images import folder_images  # imports scanner helpers

        artists = folder_images(db, root)
        if relinks:
            artist_links.mark_done(db)
        if search_index.outdated(db):
            db.commit()
            search_index.rebuild(db)  # everything, once after an update that changed how it's built
        elif changed or last != "done" or scope is not None:
            search_index.index_albums_artists(db)  # new albums and artists
        if changed or pruned_albums or covers or banners or artists:
            bump_library(db)
        job.status = "done"
    except ScanCancelled:
        # keep what was read so far; nothing is marked missing or pruned on a partial pass
        job.status = "cancelled"  # pruned_albums stays: a stop during the cover refresh comes after pruning
        if job.added or job.updated:
            search_index.index_albums_artists(db)
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
    finished = job.status
    try:
        job.finished_at = datetime.now(UTC)
        job.error_summary = "\n".join(errors) or None
        db.commit()
    finally:
        db.close()
    remove_covers(pruned_albums + reset_albums)
    if finished == "done":
        from . import album_notes  # (it imports this module)

        album_notes.lookup_missing()  # introductions for the albums without one
        from . import artist_aliases

        artist_aliases.lookup_missing()  # other names of the artists not looked up yet
        from . import playlist_import

        try:
            playlist_import.rematch_after_scan()  # imported playlists' missing songs, maybe added now
        except Exception:
            log.exception("looking for imported playlists' missing songs failed")


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
    """Stars, likes, videos and the introduction of albums about to be pruned move to the album their
    songs went to. Where the user already marked the new album, that mark stays (and the old one goes
    with the album); so does an introduction the new album already has."""
    for old, new in moves.items():
        db.execute(
            update(Album)
            .where(Album.id == new, Album.description.is_(None))
            .values(
                description=select(Album.description).where(Album.id == old).scalar_subquery(),
                description_source=select(Album.description_source).where(Album.id == old).scalar_subquery(),
            )
        )
        for model in (AlbumRating, AlbumFavorite):
            taken = select(model.user_id).where(model.album_id == new)
            db.execute(update(model).where(model.album_id == old, model.user_id.not_in(taken)).values(album_id=new))
        # NAS files (no YouTube id) always; a YouTube video unless the new album has it already
        taken = select(Video.youtube_id).where(Video.album_id == new, Video.youtube_id.is_not(None))
        db.execute(
            update(Video)
            .where(Video.album_id == old, or_(Video.youtube_id.is_(None), Video.youtube_id.not_in(taken)))
            .values(album_id=new)
        )


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
        .where(
            ~exists().where(Track.artist_id == Artist.id), ~exists().where(Album.album_artist_id == Artist.id),
            ~exists().where(TrackArtist.artist_id == Artist.id),  # a featured artist (artist_links)
        )
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


def update_album_quality(db: Session) -> None:
    """albums.quality from their songs: hires when every song is lossless and one goes past CD
    quality (more than 16 bits or 48 kHz), lossless when every song is lossless, else none."""
    db.execute(text("""
        UPDATE albums a SET quality = s.q
        FROM (
            SELECT album_id,
                   CASE WHEN count(*) FILTER (WHERE bit_depth > 0) < count(*) THEN NULL
                        WHEN max(bit_depth) > 16 OR max(sample_rate) > 48000 THEN 'hires'
                        ELSE 'lossless' END AS q
            FROM tracks WHERE missing_at IS NULL AND album_id IS NOT NULL GROUP BY album_id
        ) s
        WHERE s.album_id = a.id AND a.quality IS DISTINCT FROM s.q
    """))


def bump_library(db: Session) -> None:
    """Marks the library as changed: cached lists and ETags keyed on the old version go stale."""
    db.execute(update(LibraryState).values(version=LibraryState.version + 1, updated_at=func.now()))


def in_folder(folder: str):
    """Tracks under one top-level folder, or a folder inside one ("album/아이유/[2017] Palette": an album's
    or a chart's metadata refreshed), whatever Unicode form the path is stored in."""
    if "/" in folder:
        return func.starts_with(func.normalize(Track.file_path, text("NFC")), folder + "/")
    top = func.split_part(Track.file_path, "/", 1)
    return func.normalize(top, text("NFC")) == folder


def _find_dir(base: Path, parts: list[str]) -> Path | None:
    """The folder under base named by these parts (NFC), as it is spelled on disk (maybe NFD)."""
    for part in parts:
        try:
            base = next((base / e.name for e in os.scandir(base) if e.is_dir() and nfc(e.name) == part), None)
        except OSError:
            return None
        if base is None:
            return None
    return base


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
