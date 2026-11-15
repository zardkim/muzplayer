"""A playlist file from another player (.m3u, .m3u8, .pls) matched to the songs in the library.

Its paths are the old player's (D:\\Music\\…, /volume1/music/…, ../Music/…, file:///…), so they are
never opened: each entry is looked up by its file name among the library's songs, the one sharing
the most folders at the end of its path winning, then by the artist and title the file gives
(#EXTINF, or "Artist - Title" in the file name). What isn't found is listed as missing; several
equally good songs that are different songs (copies of one song in chart folders are one), as
ambiguous."""

import logging
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Track

log = logging.getLogger(__name__)

MAX_BYTES = 2 * 1024 * 1024
MAX_ENTRIES = 20_000
DURATION_SLACK = 3  # seconds between the file's length for a song and the library's


def decode(raw: bytes) -> str:
    """UTF-8 (.m3u8, most players now), else CP949 (Korean Windows players' .m3u)."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")


@dataclass
class Entry:
    path: str  # as written in the file
    title: str = ""  # artist - title, from #EXTINF or the .pls TitleN
    duration: float | None = None


def parse(text: str) -> list[Entry]:
    entries: list[Entry] = []
    if re.match(r"\s*\[playlist\]", text, re.I):  # .pls: FileN=, TitleN=, LengthN=
        files: dict[str, Entry] = {}
        for line in text.splitlines():
            m = re.match(r"\s*(File|Title|Length)(\d+)\s*=\s*(.*?)\s*$", line, re.I)
            if not m:
                continue
            e = files.setdefault(m[2], Entry(""))
            key = m[1].lower()
            if key == "file":
                e.path = m[3]
            elif key == "title":
                e.title = m[3]
            else:
                e.duration = _seconds(m[3])
        entries = [files[k] for k in sorted(files, key=int) if files[k].path]
    else:
        info: tuple[float | None, str] | None = None
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                m = re.match(r"#EXTINF:\s*(-?[\d.]+)[^,]*,(.*)", line, re.I)
                if m:
                    info = (_seconds(m[1]), m[2].strip())
                continue
            entries.append(Entry(line, info[1] if info else "", info[0] if info else None))
            info = None
    return entries[:MAX_ENTRIES]


def _seconds(s: str) -> float | None:
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def key(s: str) -> str:
    """For comparing names: NFC (Mac and some NAS paths keep Hangul decomposed), case and spacing."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip().casefold()


def loose(s: str) -> str:
    """For comparing titles and artists: letters and digits only."""
    return re.sub(r"[\W_]+", "", key(s))


def _plain(path: str) -> str | None:
    """An entry's path with / between folders and no drive or file:// address; None for a web address."""
    p = path.strip().strip('"')
    if p.lower().startswith("file:"):
        p = urllib.parse.unquote(urllib.parse.urlparse(p).path)
    elif re.match(r"[a-z][a-z0-9+.-]*://", p, re.I):
        return None
    elif re.search(r"%[0-9a-f]{2}", p, re.I):
        p = urllib.parse.unquote(p)
    return re.sub(r"^[a-z]:", "", p.replace("\\", "/"), flags=re.I)


def parts(path: str) -> list[str] | None:
    """The folders and file name of an entry, whatever player wrote it; None for a web address."""
    p = _plain(path)
    return None if p is None else [key(c) for c in p.split("/") if c not in ("", ".", "..")]


def file_name(path: str) -> str:
    p = _plain(path)
    return unicodedata.normalize("NFC", (p or path).rstrip("/").rsplit("/", 1)[-1])


def split_name(stem: str) -> tuple[str, str]:
    """ "01. Artist - Title" or "Artist - Title" in a file name: (artist, title); ("", stem) without."""
    stem = re.sub(r"^\s*\d{1,3}\s*[-._)]\s*", "", stem)
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


@dataclass
class Song:
    id: int
    parts: list[str]
    title: str
    artist: str
    duration: float | None


class Library:
    """The songs, indexed by file name, name without extension, and title."""

    def __init__(self, db: Session):
        self.by_name: dict[str, list[Song]] = {}
        self.by_stem: dict[str, list[Song]] = {}
        self.by_title: dict[str, list[Song]] = {}
        rows = db.execute(select(Track.id, Track.file_path, Track.title, Track.artist_text, Track.duration).where(Track.missing_at.is_(None)))
        for tid, path, title, artist, duration in rows:
            song = Song(tid, parts(path) or [], loose(title or ""), loose(artist or ""), duration)
            if not song.parts:
                continue
            name = song.parts[-1]
            self.by_name.setdefault(name, []).append(song)
            self.by_stem.setdefault(name.rsplit(".", 1)[0], []).append(song)
            if song.title:
                self.by_title.setdefault(song.title, []).append(song)


def _tail(a: list[str], b: list[str]) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _fits(song: Song, artist: str, title: str, duration: float | None) -> bool:
    if title and song.title != title:
        return False
    if artist and song.artist and artist not in song.artist and song.artist not in artist:
        return False
    if duration and song.duration and abs(song.duration - duration) > DURATION_SLACK:
        return False
    return True


def match(lib: Library, e: Entry) -> tuple[str, Song | None]:
    """(how, song): how is path (the file and folders above it), file (its name only), tags
    (artist and title), or missing / ambiguous / web (an address on the internet)."""
    p = parts(e.path)
    if p is None:
        return "web", None
    if not p:
        return "missing", None
    artist, title = split_name(e.title) if e.title else ("", "")
    if not title:
        artist, title = split_name(p[-1].rsplit(".", 1)[0])
    artist, title = loose(artist), loose(title)

    def pick(found: list[Song]) -> tuple[str, Song | None]:
        best = max(_tail(s.parts, p) for s in found)
        top = [s for s in found if _tail(s.parts, p) == best]
        if len(top) > 1:  # the same file name in several folders: the artist, title and length decide
            top = [s for s in top if _fits(s, artist, "", e.duration)] or top
        if len(top) > 1 and len({(s.artist, s.title) for s in top}) > 1:
            return "ambiguous", None
        # one song (or copies of one, as in chart folders): the first one the library got
        return ("path" if best >= 2 else "file"), min(top, key=lambda s: s.id)

    if found := lib.by_name.get(p[-1]):
        return pick(found)
    if found := lib.by_stem.get(p[-1].rsplit(".", 1)[0]):  # the same song in another format
        how, song = pick(found)
        return ("file" if song else how), song
    if title:
        found = [s for s in lib.by_title.get(title, []) if _fits(s, artist, title, e.duration)]
        if artist or e.duration:
            if len(found) == 1:
                return "tags", found[0]
            if len(found) > 1:
                return "ambiguous", None
    return "missing", None


def rematch(db: Session, playlist_ids: list[int] | None = None) -> dict:
    """The entries kept as missing (all, or these playlists'), looked for again: those found are
    added at the end of their playlist (in the file's order) and forgotten. {"found", "left"}."""
    from .api.me import _append  # (it imports this module)
    from .models import Playlist, PlaylistMissing

    q = select(PlaylistMissing).order_by(PlaylistMissing.playlist_id, PlaylistMissing.position, PlaylistMissing.id)
    if playlist_ids is not None:
        q = q.where(PlaylistMissing.playlist_id.in_(playlist_ids))
    rows = list(db.scalars(q))
    if not rows:
        return {"found": 0, "left": 0}
    lib = Library(db)
    by_list: dict[int, list[tuple[object, int]]] = {}
    for m in rows:
        how, song = match(lib, Entry(m.path, m.label or "", m.duration))
        if song is not None:
            by_list.setdefault(m.playlist_id, []).append((m, song.id))
    found = 0
    for pid, hits in by_list.items():
        playlist = db.get(Playlist, pid)
        if playlist is None:
            continue
        _append(db, playlist, [tid for _, tid in hits])
        for m, _ in hits:
            db.delete(m)
        found += len(hits)
    db.commit()
    return {"found": found, "left": len(rows) - found}


def rematch_after_scan() -> None:
    """After a scan: songs just added may be ones an imported playlist was missing."""
    from .db import SessionLocal

    with SessionLocal() as db:
        n = rematch(db)
    if n["found"]:
        log.info("imported playlists: %d missing songs found after the scan", n["found"])
