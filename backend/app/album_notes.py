"""Album introductions ("앨범 소개"), the way eztag finds them.

1. An eztag album card in the album's folder: eztag writes "[앨범카드] ….html" / "[AlbumCard] ….html"
   (older ones "[Info] ….html", or any page with <meta name="generator" content="eztag">) with the
   introduction in <div class="desc-box">. Read when the album page first opens, and again on request.
2. Otherwise an admin searches Bugs and Melon from the album page, as eztag's tag search does
   (their search and album pages, parsed the way eztag's metadata/bugs.py and melon.py do), picks
   the right album and saves its introduction; or writes one by hand.
3. After each scan, the albums with neither are looked up on their own (lookup_missing): the site
   the admin put first (Bugs by default), then the other, taking an album only when its title and
   artist are the same. Found nowhere: description_source "notfound", not asked again.
"""

import html
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bs4 import BeautifulSoup
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import appconf, search_index
from .config import settings
from .models import Album, Artist, Track
from .scanner import DISC_DIR, nfc

log = logging.getLogger(__name__)

MAX_TEXT = 20_000
REPORT_PREFIXES = ("[앨범카드]", "[AlbumCard]", "[Info]")
_DESC = re.compile(r'<div class="desc-box[^"]*"[^>]*>(.*?)</div>', re.S)
_BR = re.compile(r"<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
BUGS_SEARCH = "https://music.bugs.co.kr/search/album?q={q}"
BUGS_ALBUM = "https://music.bugs.co.kr/album/{id}"
MELON_SEARCH = "https://www.melon.com/search/album/index.htm?q={q}"
MELON_ALBUM = "https://www.melon.com/album/detail.htm?albumId={id}"
PROVIDERS = ("bugs", "melon")


# ---- the eztag album card ----
def album_dirs(db: Session, album: Album) -> list[Path]:
    """The folders the album's songs are in (a CD1/Disc 2 folder counts as its parent)."""
    dirs: dict[Path, None] = {}
    for rel in db.scalars(select(Track.file_path).where(Track.album_id == album.id, Track.missing_at.is_(None)).limit(200)):
        d = Path(rel).parent
        if DISC_DIR.match(d.name):
            d = d.parent
        dirs[settings.music_dir / d] = None
    return list(dirs)


def _report_text(page: str) -> str | None:
    m = _DESC.search(page)
    if not m:
        return None
    text = html.unescape(_TAG.sub("", _BR.sub("\n", m[1]))).strip()
    return text[:MAX_TEXT] or None


def from_report(dirs: list[Path]) -> str | None:
    """The introduction in an eztag album card in one of the folders, if there is one."""
    for d in dirs:
        try:
            pages = sorted(p for p in d.iterdir() if p.suffix.lower() == ".html" and p.is_file())
        except OSError:
            continue
        # eztag's own names first, then any page eztag says it made
        # (names compared in NFC: a NAS or a Mac may store Korean decomposed)
        pages.sort(key=lambda p: not nfc(p.name).startswith(REPORT_PREFIXES))
        for page in pages[:10]:
            try:
                text = page.read_text("utf-8", errors="ignore")
            except OSError:
                continue
            if nfc(page.name).startswith(REPORT_PREFIXES) or 'content="eztag"' in text[:4096]:
                found = _report_text(text)
                if found:
                    return found
    return None


def check_report(db: Session, album: Album, force: bool = False) -> str | None:
    """Looks for an eztag card: once, when the album page first opens (or again when asked).
    Returns the introduction found."""
    if not force and album.description_source is not None:
        return None
    found = from_report(album_dirs(db, album))
    if found:
        album.description, album.description_source = found, "eztag"
    elif album.description_source is None:
        album.description_source = "none"  # looked: none there
    db.commit()
    return found


# ---- Bugs and Melon ----
def _get(url: str, referer: str) -> BeautifulSoup:
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Referer": referer, "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return BeautifulSoup(resp.read().decode("utf-8", errors="replace"), "html.parser")


def _year(text: str) -> int | None:
    m = re.search(r"(19|20)\d{2}", text or "")
    return int(m[0]) if m else None


def _bugs_artists(links) -> str:
    names = []
    for a in links:
        if "connect" in (a.get("href") or "").lower():
            continue
        text = re.sub(r"CONNECT\s*아티스트?|아티스트명\s*공간\s*초과시\s*더보기\s*버튼\s*노출|더보기\s*버튼\s*노출", "",
                      a.get_text(strip=True), flags=re.I).strip()
        if text and text not in names:
            names.append(text)
    return ", ".join(names)


def _search_bugs(q: str, limit: int) -> list[dict]:
    soup = _get(BUGS_SEARCH.format(q=urllib.parse.quote(q)), "https://music.bugs.co.kr/")
    out = []
    for li in soup.select("ul.albumList li"):
        album_id = next((m[1] for a in li.find_all("a", href=True) if (m := re.search(r"/album/(\d+)", a["href"]))), "")
        if not album_id:
            continue
        title = li.select_one(".albumTitle a, a.albumTitle")
        date = li.select_one("time, .info-release, span.date")
        img = li.select_one("img")
        out.append({
            "provider": "bugs", "id": album_id,
            "title": title.get_text(strip=True) if title else "",
            "artist": _bugs_artists(li.select(".artistName a, p.artist a, a.artist")),
            "year": _year(date.get_text(strip=True) if date else ""),
            "cover": (img.get("src") or "").split("?")[0] if img else "",
            "url": BUGS_ALBUM.format(id=album_id),
        })
        if len(out) >= limit:
            break
    return out


def _search_melon(q: str, limit: int) -> list[dict]:
    soup = _get(MELON_SEARCH.format(q=urllib.parse.quote(q)), "https://www.melon.com/")
    box = soup.find("div", class_="d_album_list")
    out = []
    for li in box.find_all("li", class_="album11_li") if box else []:
        thumb = li.find("a", class_="thumb")
        m = re.search(r"goAlbumDetail\(['\"]?(\d+)", (thumb.get("href", "") + thumb.get("onclick", "")) if thumb else "")
        if not m:
            continue
        dt = li.find("dt")
        title = dt.find("a", class_="ellipsis") if dt else None
        artist = li.find("dd", class_="atistname")
        links = [a for a in artist.find_all("a") if not a.find_parent(class_=re.compile("screen_out|blind"))] if artist else []
        names = list(dict.fromkeys(a.get_text(strip=True) for a in links if a.get_text(strip=True)))
        img = li.find("img")
        out.append({
            "provider": "melon", "id": m[1],
            "title": title.get_text(strip=True) if title else "",
            "artist": ", ".join(names) or (artist.get_text(" ", strip=True) if artist else ""),
            "year": _year(" ".join(dd.get_text(strip=True) for dd in li.find_all("dd"))),
            "cover": (img.get("src") or "").split("?")[0] if img else "",
            "url": MELON_ALBUM.format(id=m[1]),
        })
        if len(out) >= limit:
            break
    return out


def search(q: str, limit: int = 8) -> list[dict]:
    """Albums matching q on Bugs and Melon (both at once), Bugs first. A site that fails is left out."""
    def one(provider: str) -> list[dict]:
        try:
            return (_search_bugs if provider == "bugs" else _search_melon)(q, limit)
        except Exception as exc:  # noqa: BLE001 - a site down or changed: the other may still answer
            log.warning("%s album search failed: %s", provider, exc)
            return []

    with ThreadPoolExecutor(2) as pool:
        return [item for found in pool.map(one, PROVIDERS) for item in found]


def fetch(provider: str, album_id: str) -> str | None:
    """The introduction on a Bugs or Melon album page (None when it has none)."""
    if provider == "bugs":
        soup = _get(BUGS_ALBUM.format(id=album_id), "https://music.bugs.co.kr/")
        el = (soup.select_one("div.albumContents span") or soup.select_one("div.albumDesc span")
              or soup.select_one("p#albumContents span") or soup.select_one("p.albumContents span"))
    else:
        soup = _get(MELON_ALBUM.format(id=album_id), "https://www.melon.com/")
        el = soup.find("div", id="d_video_summary") or soup.select_one("div.dtl_albuminfo")
    text = el.get_text("\n", strip=True) if el else ""
    return text[:MAX_TEXT] or None


# ---- looked up after a scan ----
LOOKUP_PER_RUN = 300  # albums a scan looks up (the newest first); the rest on the next scans
LOOKUP_PAUSE = 1.0  # seconds between albums: the sites aren't hurried
_lookup_lock = threading.Lock()


# "How You Like That - Single", "Dancing Queen (Single)", "봄날 - EP": the sites list the title alone
_RELEASE = re.compile(r"\s*(?:[-–]\s*(?:single|ep)|[(\[]\s*(?:single|ep|싱글|미니앨범)\s*[)\]])\s*$", re.I)


def _core(title: str) -> str:
    return _RELEASE.sub("", title).strip() or title


def _same(a: str, b: str) -> bool:
    a, b = search_index.norm(_core(a)), search_index.norm(_core(b))
    return bool(a and b) and (a == b or a.replace(" ", "") == b.replace(" ", ""))


def _artist_fits(want: str, found: str) -> bool:
    w, f = search_index.norm(want).replace(" ", ""), search_index.norm(found).replace(" ", "")
    return not w or (bool(f) and (w in f or f in w))


class Unreachable(Exception):
    """A site didn't answer: `everywhere` when neither did."""

    def __init__(self, everywhere: bool):
        super().__init__("notes_unreachable")
        self.everywhere = everywhere


def find_notes(title: str, artist: str) -> tuple[str, str] | None:
    """(introduction, source) for the album with this title and artist, from the first site that has
    one; None when neither does. Raises Unreachable when a site that might have it didn't answer."""
    first = appconf.get("notes_provider")
    order = ("melon", "bugs") if first == "melon" else ("bugs", "melon")
    q = f"{artist} {_core(title)}".strip()
    failed = 0
    for provider in order:
        try:
            items = (_search_bugs if provider == "bugs" else _search_melon)(q, 10)
            same = [it for it in items if _same(it["title"], title)]
            # the artist as written here, or (written another way: "블랙핑크" for "BLACKPINK") one of the
            # site's own first few answers to the artist and title
            hit = next((it for it in same if _artist_fits(artist, it["artist"])), None) or next((it for it in same if it in items[:3] and artist), None)
            text = fetch(provider, hit["id"]) if hit else None
        except Exception as exc:  # noqa: BLE001 - a site down or changed: the other may still answer
            log.warning("%s album notes for %r: %s", provider, q, exc)
            failed += 1
            continue
        if text:
            return text, f"{provider}:{hit['id']}"
    if failed:
        raise Unreachable(failed == len(order))
    return None


def lookup_missing() -> bool:
    """Looks up introductions for the albums without one, in the background (after a scan)."""
    if appconf.get("notes_provider") == "off" or not _lookup_lock.acquire(blocking=False):
        return False
    threading.Thread(target=_lookup, daemon=True, name="album-notes").start()
    return True


def _lookup() -> None:
    from .db import SessionLocal  # (the app's engine, made once the app starts)

    try:
        with SessionLocal() as db:
            ids = list(db.scalars(
                select(Album.id)
                .where(Album.description.is_(None), or_(Album.description_source.is_(None), Album.description_source == "none"),
                       Album.kind != "chart")
                .order_by(Album.created_at.desc(), Album.id.desc())
                .limit(LOOKUP_PER_RUN)
            ))
            for album_id in ids:
                album = db.get(Album, album_id)
                if album is None or album.description is not None:
                    continue
                if album.description_source is None and check_report(db, album):
                    continue  # an eztag card in its folder
                artist = db.get(Artist, album.album_artist_id) if album.album_artist_id else None
                db.commit()  # don't hold a pool connection while the sites answer
                try:
                    found = find_notes(album.title, artist.name if artist else "")
                except Unreachable as exc:
                    if exc.everywhere:
                        return  # neither site answers: the next scan tries again
                    continue  # one didn't: this album again next time
                album = db.get(Album, album_id)
                if album is None or album.description is not None:
                    continue
                album.description, album.description_source = found if found else (None, "notfound")
                db.commit()
                time.sleep(LOOKUP_PAUSE)
    except Exception:  # noqa: BLE001 - a lookup that fails must not touch the scan
        log.exception("album notes lookup failed")
    finally:
        _lookup_lock.release()
