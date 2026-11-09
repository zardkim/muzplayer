"""Songs and their artists, as people mean them rather than as the tag spells them.

A tag's artist is often several: "윤슬 feat. Marlow", "Zion.T x Crush", "박명수, 아이유". Each song
gets every one of them (TrackArtist: the main ones, then the featured), so a featured artist's page
lists the song too, and Track.artist_id is the first main one. Splitting stays careful, since some
names hold the same marks ("Earth, Wind & Fire", "Simon & Garfunkel"):

  - "feat." / "ft." / "featuring" / "(Feat. …)" / "(with …)": always split (main, then featured);
  - "," "&" " x " "×" ";": only when the whole isn't a known artist and every piece is one.

An artist is known when it stands on its own somewhere: an album's artist, a song's whole artist,
an artist other names were found for (artist_aliases: so it exists), or a name merged into one.

Also the artists' sort keys: the script first (한글, Latin, then other letters, then digits and
marks), a leading "The" / "A" / "An" left out, and the Korean name used when the artist has one
(머라이어 캐리 sorts under ㅁ; sort_own keeps its own name's place).

Done again for the whole library after every scan (only what changed is written), and once after an
update that changed how (LINKS_VERSION).
"""

import logging
import re
import threading
import unicodedata

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from . import search_index
from .models import Album, Artist, LibraryState, NameAlias, Track, TrackArtist

log = logging.getLogger(__name__)

LINKS_VERSION = 1
SEP = " / "  # between a song's tag values in Track.artist_text (scanner._apply_tags)
NOT_SPLIT = {"various artists", "여러 아티스트", "va", "v.a.", "v.a"}
_FEAT = re.compile(r"\s*[(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s+([^)\]]+)[)\]]\s*$|\s+(?:feat\.?|ft\.?|featuring)\s+(.+)$", re.I)
_SPLIT = re.compile(r"\s*(?:,|&|;|×|\s[xX]\s)\s*")
_ARTICLE = re.compile(r"^(?:the|a|an)\s+(?=\S)", re.I)
_lock = threading.Lock()


def key(name: str) -> str:
    return search_index.norm(name).replace(" ", "")


def split(value: str, known: set[str]) -> list[tuple[str, str]]:
    """One tag value -> [(name, "main" | "feat")]."""
    value = " ".join(value.split())
    if not value or value.casefold() in NOT_SPLIT:
        return [(value, "main")] if value else []
    out: list[tuple[str, str]] = []
    m = _FEAT.search(value)
    main, featured = (value[: m.start()].strip(), (m.group(1) or m.group(2)).strip()) if m else (value, "")
    out += [(n, "main") for n in _pieces(main, known)]
    if featured:
        out += [(n, "feat") for n in _pieces(featured, known)]
    return out or [(value, "main")]


def _pieces(text: str, known: set[str]) -> list[str]:
    if not text:
        return []
    if key(text) in known:
        return [text]
    parts = [p for p in _SPLIT.split(text) if p.strip()]
    if len(parts) > 1 and all(key(p) in known for p in parts):
        return parts
    return [text]


def _script(ch: str) -> str:
    if "가" <= ch <= "힣" or "ㄱ" <= ch <= "ㆎ":
        return "1"
    if ch.isascii() and ch.isalpha() or unicodedata.category(ch).startswith("L") and "LATIN" in unicodedata.name(ch, ""):
        return "2"
    if ch.isalpha():
        return "3"
    return "4"


def _fold(text: str) -> str:
    """Latin accents off (Ångström sorts with A); Hangul stays whole (NFKD would split it into jamo)."""
    return "".join(
        "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)) if _script(ch) == "2" else ch
        for ch in text
    )


def sort_key(name: str) -> str:
    text = _ARTICLE.sub("", " ".join(unicodedata.normalize("NFKC", name).split())).casefold()
    start = next((i for i, c in enumerate(text) if c.isalnum()), 0)  # "(G)I-DLE" sorts at its G
    text = _fold(text[start:]) or text
    return (_script(text[0] if text else " ") + text)[:500]


def sort_keys(name: str, others: list[str]) -> tuple[str, str]:
    """(by its Korean name when it has one, by its own name)."""
    own = sort_key(name)
    if own.startswith("1"):
        return own, own
    korean = next((o for o in others if sort_key(o).startswith("1")), None)
    return (sort_key(korean) if korean else own), own


def initial_range(initial: str) -> tuple[str, str] | None:
    """The sort-key range of an index letter: ㄱ..ㅎ (with its doubled one), A..Z, "etc" (other
    scripts), "#" (digits and marks)."""
    jamo = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
    shown = "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ"
    if initial in shown:
        i = jamo.index(initial)
        j = i + 1
        while j < len(jamo) and jamo[j] not in shown:  # ㄱ takes ㄲ, ㄷ ㄸ, ㅂ ㅃ, ㅅ ㅆ, ㅈ ㅉ
            j += 1
        start = "1" + chr(0xAC00 + i * 588)
        end = "1" + (chr(0xAC00 + j * 588) if j < len(jamo) else "힤")
        return start, end
    if len(initial) == 1 and "A" <= initial <= "Z":
        return "2" + initial.lower(), "2" + chr(ord(initial.lower()) + 1)
    if initial == "etc":
        return "3", "4"
    if initial == "#":
        return "4", "5"
    return None


INITIALS = list("ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ") + [chr(c) for c in range(ord("A"), ord("Z") + 1)] + ["etc", "#"]


def initial_of(sort: str) -> str:
    """The index letter of a sort key."""
    for letter in INITIALS:
        span = initial_range(letter)
        if span and span[0] <= sort < span[1]:
            return letter
    return "#"


def relink(db: Session) -> int:
    """Every song's artists again (from Track.artist_text); returns how many songs changed."""
    merged = {a.name: a.target for a in db.scalars(select(NameAlias).where(NameAlias.kind == "artist"))}
    ids = dict(db.execute(select(Artist.name, Artist.id)).all())
    known = {key(n) for n in db.scalars(select(Artist.name).where(Artist.id.in_(select(Album.album_artist_id))))}
    known |= {key(n) for n in db.scalars(select(Artist.name).where(Artist.aliases.is_not(None)))}
    known |= {key(t) for t in merged.values()}
    tracks = db.execute(select(Track.id, Track.artist_text, Track.artist_id)).all()
    # a song's whole artist, when nothing in it could be a split mark
    known |= {key(text) for _, text, _ in tracks if text and SEP not in text and not _FEAT.search(text) and not _SPLIT.search(text)}
    known.discard("")
    current: dict[int, list[tuple[int, str]]] = {}
    for track_id, artist_id, role in db.execute(
        select(TrackArtist.track_id, TrackArtist.artist_id, TrackArtist.role).order_by(TrackArtist.track_id, TrackArtist.position)
    ):
        current.setdefault(track_id, []).append((artist_id, role))

    def artist_id(name: str) -> int:
        name = merged.get(name, name)[:500]
        if name not in ids:
            row = Artist(name=name, sort_name=sort_key(name), sort_own=sort_key(name))
            db.add(row)
            db.flush()
            ids[name] = row.id
        return ids[name]

    changed = 0
    main_ids: list[dict] = []
    gone: list[int] = []  # songs whose links are redone (in batches: 100k songs on a first run)
    rows: list[dict] = []
    for track_id, text, old_main in tracks:
        wanted: list[tuple[int, str]] = []
        for value in (text or "").split(SEP):
            for name, role in split(value, known):
                aid = artist_id(name)
                if all(aid != a for a, _ in wanted):
                    wanted.append((aid, role))
        if wanted != current.get(track_id, []):
            if track_id in current:
                gone.append(track_id)
            rows += [{"track_id": track_id, "artist_id": a, "position": i, "role": r} for i, (a, r) in enumerate(wanted)]
            changed += 1
        main = next((a for a, r in wanted if r == "main"), None)
        if main is not None and main != old_main:
            main_ids.append({"id": track_id, "artist_id": main})
    for i in range(0, len(gone), 5000):
        db.execute(delete(TrackArtist).where(TrackArtist.track_id.in_(gone[i : i + 5000])))
    for i in range(0, len(rows), 5000):
        db.execute(insert(TrackArtist), rows[i : i + 5000])
    for i in range(0, len(main_ids), 2000):
        db.execute(update(Track), main_ids[i : i + 2000])
    return changed + len(main_ids)  # (an artist left with nothing, a whole "A feat. B": scanner.prune_orphans)


def outdated(db: Session) -> bool:
    return (db.scalar(select(LibraryState.links_version)) or 0) != LINKS_VERSION


def mark_done(db: Session) -> None:
    db.execute(update(LibraryState).values(links_version=LINKS_VERSION, version=LibraryState.version + 1))


def relink_in_background() -> None:
    """At startup after an update that changed the links: done now rather than at the next scan."""
    from .db import SessionLocal
    from .scanner import prune_orphans, scan_lock

    def run() -> None:
        with SessionLocal() as db:
            if not outdated(db):
                return
        lock = scan_lock()
        lock.acquire()  # after a scan (or the search index) running now
        try:
            with SessionLocal() as db:
                if not outdated(db):
                    return  # that scan linked them
                n = relink(db)
                prune_orphans(db)  # artists left with nothing
                search_index.index_albums_artists(db)  # sort keys of the artists made
                mark_done(db)
                db.commit()
                log.info("song artists linked (%d songs changed)", n)
        except Exception:
            log.exception("linking song artists failed")
        finally:
            lock.release()

    threading.Thread(target=run, daemon=True, name="artist-links").start()
