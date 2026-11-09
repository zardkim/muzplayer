"""Artists' other names: 머라이어 캐리 for Mariah Carey, IU for 아이유, so a search in either finds
them (search_index puts them in the artist's search_text; songs and albums are found through their
artist). Looked up after a scan, a few hundred artists a run, from:

  1. MusicBrainz: the artist whose name (or one of its names) is ours, when only one such artist is
     a close match (no guessing between namesakes); its Korean and English names.
  2. Wikidata, through that MusicBrainz artist's id (P434): its Korean and English names and their
     usual spellings (머라이어 케리, 머라이어캐리).
  3. Bugs' artist search: "Mariah Carey(머라이어 캐리)", when only one artist there has our name.

Only Hangul and Latin names are kept, at most MAX_ALIASES. An admin adds names by hand or hides
wrong ones (api/library.py PUT /artists/{id}/aliases); a later lookup keeps both. Looked up again
after STALE. A site that doesn't answer is skipped (the next scan tries again).
"""

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import appconf, search_index
from .album_notes import _get as get_page
from .config import settings
from .models import Artist, Track

log = logging.getLogger(__name__)

MAX_ALIASES = 8
PER_RUN = 200
STALE = timedelta(days=90)
MB_SEARCH = "https://musicbrainz.org/ws/2/artist/"
WD_API = "https://www.wikidata.org/w/api.php"
BUGS_SEARCH = "https://music.bugs.co.kr/search/artist?q={q}"
USER_AGENT = f"muzplayer/{settings.version} (self-hosted music player; https://gitea.nurilab.pe.kr/nuricom/muzplayer)"
MB_PAUSE = 1.1  # MusicBrainz: one request a second
_SCRIPT_OK = re.compile(r"^[\sA-Za-z0-9À-ɏ가-힣ㄱ-ㆎ&'’.,!?()\-+/:·]+$")
_PAIR = re.compile(r"^(.*\S)\(([^()]+)\)$")  # "Mariah Carey(머라이어 캐리)" (not "Mariah Carey (Karaoke)")
_lock = threading.Lock()


class Unreachable(Exception):
    pass


def _json(url: str, params: dict) -> dict:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < 2:  # too fast (MusicBrainz): a moment, then again
                time.sleep(3 * (attempt + 1))
                continue
            raise Unreachable(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - any other failure: this source is out for now
            raise Unreachable(str(exc)) from exc
    raise Unreachable("no answer")


def _same(a: str, b: str) -> bool:
    return search_index.norm(a) == search_index.norm(b) and bool(search_index.norm(a))


# a description given as a name ("South Korean singer"), not a name
_DESCRIPTION = re.compile(r"\b(singer|band|group|rapper|musician|duo|trio|composer|songwriter|vocalist)\b|가수|그룹|밴드|작곡가", re.I)


def _usable(name: str) -> bool:
    return bool(name.strip()) and len(name) <= 200 and bool(_SCRIPT_OK.match(name)) and not _DESCRIPTION.search(name)


def from_musicbrainz(name: str) -> tuple[str | None, list[str]]:
    """(its MusicBrainz id, its Korean and English names) when one artist clearly is ours."""
    quoted = name.replace('"', " ")
    data = _json(MB_SEARCH, {"query": f'artist:"{quoted}" OR alias:"{quoted}"', "fmt": "json", "limit": 10})
    fits = [
        a for a in data.get("artists", [])
        if int(a.get("score", 0)) >= 90 and (_same(a.get("name", ""), name) or any(_same(x.get("name", ""), name) for x in a.get("aliases") or []))
    ]
    if len(fits) != 1:
        return None, []  # none, or namesakes: no guessing
    a = fits[0]
    names = [a.get("name", "")]
    for x in a.get("aliases") or []:
        locale = (x.get("locale") or "")[:2]
        if locale in ("ko", "en") or (not locale and re.search(r"[가-힣]", x.get("name", ""))):
            names.append(x.get("name", ""))
    return a.get("id"), names


def from_wikidata(mbid: str) -> list[str]:
    """Korean and English names of the Wikidata item with this MusicBrainz artist id."""
    found = _json(WD_API, {"action": "query", "list": "search", "srsearch": f"haswbstatement:P434={mbid}", "format": "json", "srlimit": 2})
    hits = found.get("query", {}).get("search", [])
    if len(hits) != 1:
        return []
    qid = hits[0]["title"]
    data = _json(WD_API, {"action": "wbgetentities", "ids": qid, "props": "labels|aliases", "languages": "ko|en", "format": "json"})
    entity = data.get("entities", {}).get(qid, {})
    names = [v.get("value", "") for v in entity.get("labels", {}).values()]
    for lang in ("ko", "en"):
        names += [v.get("value", "") for v in entity.get("aliases", {}).get(lang, [])]
    return names


def from_bugs(name: str) -> list[str]:
    """Bugs shows "Name(Other name)": both, when only one artist there has our name."""
    try:
        page = get_page(BUGS_SEARCH.format(q=urllib.parse.quote(name)), "https://music.bugs.co.kr/")
    except Exception as exc:  # noqa: BLE001
        raise Unreachable(str(exc)) from exc
    fits = []
    for el in page.select("figure.artistInfo figcaption a.artistTitle, .artistInfo .artistTitle")[:10]:
        text = " ".join(el.get_text(" ", strip=True).split())
        m = _PAIR.match(text)
        both = [m.group(1), m.group(2)] if m else [text]
        if any(_same(n, name) for n in both):
            fits.append(both)
    return fits[0] if len(fits) == 1 else []


def find(name: str) -> tuple[list[tuple[str, str]], bool, bool]:
    """Other names of `name` with where each came from, whether every source answered, and whether any did."""
    out: list[tuple[str, str]] = []
    answered = True
    failed = 0
    mbid = None
    try:
        mbid, names = from_musicbrainz(name)
        out += [(n, "musicbrainz") for n in names]
    except Unreachable as exc:
        log.info("artist aliases: MusicBrainz: %s", exc)
        answered = False
        failed += 1
    if mbid:
        try:
            out += [(n, "wikidata") for n in from_wikidata(mbid)]
        except Unreachable as exc:
            log.info("artist aliases: Wikidata: %s", exc)
            answered = False
    try:
        out += [(n, "bugs") for n in from_bugs(name)]
    except Unreachable as exc:
        log.info("artist aliases: Bugs: %s", exc)
        answered = False
        failed += 1
    return out, answered, failed < 2


def merge(current: list | None, found: list[tuple[str, str]], name: str) -> list[dict]:
    """The new list: names added by hand and hidden ones kept, what was found after them."""
    kept = [a for a in current or [] if a.get("source") == "manual" or a.get("hidden")]
    seen = {search_index.norm(name).replace(" ", "")} | {search_index.norm(a["name"]).replace(" ", "") for a in kept}
    out = list(kept)
    for alias, source in found:
        alias = " ".join(alias.split())
        key = search_index.norm(alias).replace(" ", "")
        if not key or key in seen or not _usable(alias):
            continue
        seen.add(key)
        out.append({"name": alias, "source": source, "hidden": False})
    visible = [a for a in out if not a.get("hidden")]
    hidden = [a for a in out if a.get("hidden")]
    return visible[:MAX_ALIASES] + hidden


def visible(artist: Artist) -> list[str]:
    return [a["name"] for a in artist.aliases or [] if not a.get("hidden")]


def lookup_missing() -> bool:
    """Looks up the artists never looked up (or long ago), in the background (after a scan)."""
    if appconf.get("artist_aliases") == "off" or not _lock.acquire(blocking=False):
        return False
    threading.Thread(target=_lookup, daemon=True, name="artist-aliases").start()
    return True


def running() -> bool:
    return _lock.locked()


def _lookup() -> None:
    from .db import SessionLocal  # (the app's engine, made once the app starts)
    from .scanner import bump_library

    changed = 0
    try:
        with SessionLocal() as db:
            has_songs = select(Track.id).where(Track.artist_id == Artist.id, Track.missing_at.is_(None)).exists()
            ids = list(db.scalars(
                select(Artist.id)
                .where(has_songs, or_(Artist.aliases_checked_at.is_(None), Artist.aliases_checked_at < datetime.now(UTC) - STALE))
                .order_by(Artist.aliases_checked_at.nulls_first(), Artist.id)
                .limit(PER_RUN)
            ))
            for artist_id in ids:
                artist = db.get(Artist, artist_id)
                if artist is None:
                    continue
                name = artist.name
                db.commit()  # don't hold a pool connection while the sites answer
                found, answered, reached = find(name)
                if not reached:
                    log.info("artist aliases: sites not answering, stopping for now")
                    break
                artist = db.get(Artist, artist_id)
                if artist is None:
                    continue
                new = merge(artist.aliases, found, artist.name)
                if new != (artist.aliases or []):
                    artist.aliases = new
                    changed += 1
                if answered:
                    artist.aliases_checked_at = datetime.now(UTC)
                db.commit()
                time.sleep(MB_PAUSE)
            if changed:
                search_index.index_albums_artists(db)
                bump_library(db)
                db.commit()
                log.info("artist aliases: %d artists got other names", changed)
    except Exception:  # noqa: BLE001 - a lookup that fails must not touch anything else
        log.exception("artist aliases lookup failed")
    finally:
        _lock.release()
