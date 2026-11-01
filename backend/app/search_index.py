"""The search index: what search matches against, worked out when the library is scanned.

Each song, album and artist keeps one `search_text` (with a trigram index) holding its words in a
form that forgives how people type:

  - width, case, accents of form and punctuation ignored ("Don't" = "dont", "ＩＵ" = "iu");
  - each field also without its spaces ("밤 편지" is found by "밤편지");
  - the initial consonants of its Korean ("ㅂㅍㅈ" finds "밤편지", "ㅇㅇㅇ" finds "아이유").

A query matches when every word of it is found (in any order, in any field: "아이유 밤편지").

Songs get theirs when a scan files them (scanner._classify), albums and artists after each scan.
When the way the index is built changes (SEARCH_VERSION), the next start or scan builds it again
for everything (rebuild); an admin can ask for that too.
"""

import logging
import re
import threading
import unicodedata

from sqlalchemy import ColumnElement, false, select, update
from sqlalchemy.orm import Session

from .models import Album, Artist, LibraryState, Track

log = logging.getLogger(__name__)

SEARCH_VERSION = 1
MAX_WORDS = 8
BATCH = 2000
_NOT_WORD = re.compile(r"[^\w]+|_")  # punctuation and spaces (\w keeps letters of every script and digits)
_APOSTROPHE = re.compile(r"['\u2019`\u00b4]")  # inside a word: "don't" is "dont"
# the 19 initial consonants of a Hangul syllable, as typed (compatibility jamo)
_CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def norm(text: str | None) -> str:
    """Words as compared: NFKC, case-folded, apostrophes dropped, other punctuation as spaces."""
    text = _APOSTROPHE.sub("", unicodedata.normalize("NFKC", text or "").casefold())
    return " ".join(_NOT_WORD.sub(" ", text).split())


def initials(text: str | None) -> str:
    """The initial consonants of the Korean syllables in text ("밤편지 (Live)" -> "ㅂㅍㅈ")."""
    out = []
    for ch in unicodedata.normalize("NFC", text or ""):
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out.append(_CHOSEONG[code // 588])
    return "".join(out)


def index_text(*fields: str | None) -> str:
    """The search_text for these fields (a song: title, artists, album)."""
    parts: dict[str, None] = {}
    for field in fields:
        words = norm(field)
        if not words:
            continue
        parts[words] = None
        parts[words.replace(" ", "")] = None
        first = initials(field)
        if len(first) > 1:
            parts[norm(first)] = None  # through norm too: NFKC turns ㅂ into its conjoining form
    return " ".join(parts)[:4000]


def _escape(word: str) -> str:
    return word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def matches(column, q: str) -> list[ColumnElement[bool]]:
    """Conditions for a query: each of its words somewhere in the column's search_text."""
    words = list(dict.fromkeys(norm(q).split()))[:MAX_WORDS]
    if not words:  # only punctuation ("!!!"): nothing matches, rather than everything
        return [false()]
    return [column.like(f"%{_escape(w)}%") for w in words]


# ---- building it ----
_rebuild_lock = threading.Lock()


def index_albums_artists(db: Session) -> None:
    """Albums and artists (a few thousand rows: done whole after each scan or merge)."""
    names = dict(db.execute(select(Artist.id, Artist.name)).all())
    rows = []
    for artist_id, name in names.items():
        rows.append({"id": artist_id, "search_text": index_text(name)})
    _write(db, Artist, rows)
    rows = [
        {"id": album_id, "search_text": index_text(title, names.get(artist_id))}
        for album_id, title, artist_id in db.execute(select(Album.id, Album.title, Album.album_artist_id))
    ]
    _write(db, Album, rows)


def _write(db: Session, model, rows: list[dict]) -> None:
    """Only the rows whose text changed (an UPDATE per row costs on a NAS)."""
    current = dict(db.execute(select(model.id, model.search_text)).all())
    changed = [r for r in rows if current.get(r["id"]) != r["search_text"]]
    for i in range(0, len(changed), BATCH):
        db.execute(update(model), changed[i : i + BATCH])


def index_tracks(db: Session) -> int:
    """Every song again (after SEARCH_VERSION changed). Returns how many changed."""
    albums = dict(db.execute(select(Album.id, Album.title)).all())
    done = 0
    last = 0
    while True:
        rows = db.execute(
            select(Track.id, Track.title, Track.artist_text, Track.album_id, Track.search_text)
            .where(Track.id > last).order_by(Track.id).limit(BATCH)
        ).all()
        if not rows:
            return done
        changed = [
            {"id": i, "search_text": text}
            for i, title, artist, album_id, old in rows
            if (text := index_text(title, artist, albums.get(album_id))) != old
        ]
        if changed:
            db.execute(update(Track), changed)
        db.commit()
        done += len(changed)
        last = rows[-1][0]


def outdated(db: Session) -> bool:
    return (db.scalar(select(LibraryState.search_version)) or 0) != SEARCH_VERSION


def rebuild(db: Session) -> None:
    """The whole index, when it is out of date. Run with the scan lock held (by the scan, or by
    rebuild_in_background), so songs are not being filed meanwhile."""
    if not outdated(db) or not _rebuild_lock.acquire(blocking=False):
        return
    try:
        log.info("building the search index")
        index_albums_artists(db)  # first: a few seconds, and album/artist search needs it
        db.commit()
        n = index_tracks(db)
        db.execute(update(LibraryState).values(search_version=SEARCH_VERSION, version=LibraryState.version + 1))
        db.commit()
        log.info("search index built (%d songs changed)", n)
    finally:
        _rebuild_lock.release()


def rebuild_in_background() -> None:
    """At startup: an update that changed the index builds it now rather than at the next scan
    (scans may be hours apart). Waits its turn if a scan is running; that scan builds it anyway."""
    from .db import SessionLocal
    from .scanner import scan_lock

    def run() -> None:
        with SessionLocal() as db:
            if not outdated(db):
                return
        lock = scan_lock()
        if not lock.acquire(blocking=False):
            return
        try:
            with SessionLocal() as db:
                rebuild(db)
        except Exception:
            log.exception("building the search index failed")
        finally:
            lock.release()

    threading.Thread(target=run, daemon=True, name="search-index").start()
