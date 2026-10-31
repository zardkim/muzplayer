"""Synced lyrics (LRC) fetched for songs that have none, the way eztag's "LRC 가져오기" does.

When a song plays, the app asks for its lyrics (api/library.py). A song without synced lyrics of its
own (no .lrc next to it, none in the tags) gets them looked up once and kept in the database (the
library is read-only): by the file itself on AlSong (an exact match of its audio), then by title and
artist on Bugs, LRCLIB and AlSong. Nothing found is remembered too, and tried again after RETRY_DAYS.
"""

import hashlib
import html
import json
import logging
import re
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from .lyrics import parse
from .models import FetchedLyrics, Track

log = logging.getLogger(__name__)

RETRY_DAYS = 30
TIMEOUT = 5
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# lookups at once; a request finding none free doesn't wait (it would hold a server thread that songs
# are streamed from): it answers without and the next play of the song tries again
_slots = threading.BoundedSemaphore(2)
_busy: set[int] = set()
_busy_lock = threading.Lock()


def _norm(s: str) -> str:
    s = re.sub(r"[^\w\s]", "", (s or "").lower())
    return " ".join(s.split())


def _clean_title(title: str) -> str:
    """"Song (feat. X) [Live]" -> "Song": what the lyrics sites list it as."""
    t = re.sub(r"\s+(?:feat\.?|ft\.?|with)\s+.+$", "", title, flags=re.I)
    return re.sub(r"\s*[(\[{][^)\]}]*[)\]}]", "", t).strip() or title


def _first_artist(artist: str) -> str:
    return re.split(r"\s*(?:/|,|&| feat\.? | ft\.? )\s*", artist or "", maxsplit=1, flags=re.I)[0].strip()


def _get(url: str, headers: dict | None = None, data: bytes | None = None) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": _UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


# ---- AlSong (unofficial SOAP service; eztag metadata/alsong.py) ----
ALSONG_URL = "http://lyrics.alsong.co.kr/alsongwebservice/service1.asmx"
_ENC = (
    "8582df6473c019a3186a2974aa1e034ae1b2bbb2e7c99575aadc475fcddd997d7"
    "4bbc1ce3d50b9900282903ee9eb60ae8c5bbf27484441bacb41ecf912840269664"
    "1655ff38c2cbbf3c81396034a883af2d82e0545ec32170bddc7c141208e7255e36"
    "7e5b5ebd81750226856f5405ec3ad7b6f8600c32c2718c4c525bfe34666"
)
_SOAP = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:ns1="ALSongWebServer">
<SOAP-ENV:Body><ns1:{op}><ns1:encData>{enc}</ns1:encData><ns1:stQuery>{query}</ns1:stQuery></ns1:{op}></SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""


def _alsong(op: str, query: str) -> str | None:
    body = _SOAP.format(op=op, enc=_ENC, query=query).encode()
    headers = {"Content-Type": "application/soap+xml; charset=utf-8", "SOAPAction": f'"ALSongWebServer/{op}"', "User-Agent": "gSOAP/2.7"}
    req = urllib.request.Request(ALSONG_URL, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            content = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 500:  # a SOAP fault comes as 500: nothing found
            raise
        return None
    try:
        el = ET.fromstring(content).find(".//{*}strLyric")
    except ET.ParseError:
        return None
    if el is None or not el.text or "[" not in el.text:
        return None
    return re.sub(r"<br\s*/?>", "\n", el.text.strip(), flags=re.I)


def _alsong_checksum(path: Path) -> str | None:
    """MD5 of 160 KB of audio (after an MP3's ID3v2 tag): how AlSong knows a file."""
    with open(path, "rb") as f:
        raw = f.read(4 * 1024 * 1024)
    offset = 0
    if path.suffix.lower() == ".mp3" and raw[:3] == b"ID3" and len(raw) >= 10:
        size = 0
        for b in raw[6:10]:
            size = (size << 7) | (b & 0x7F)
        offset = 10 + size
    chunk = raw[offset : offset + 163840]
    return hashlib.md5(chunk).hexdigest() if len(chunk) >= 1024 else None


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def alsong_by_file(path: Path) -> str | None:
    checksum = _alsong_checksum(path)
    if not checksum:
        return None
    query = (f"<ns1:strChecksum>{checksum}</ns1:strChecksum><ns1:strVersion>2.11</ns1:strVersion>"
             f"<ns1:strMACAddress>{uuid.getnode():012X}</ns1:strMACAddress><ns1:strIPAddress>{_local_ip()}</ns1:strIPAddress>")
    return _alsong("GetLyric8", query)


def alsong_by_name(title: str, artist: str) -> str | None:
    for t, a in ((title, artist), (_clean_title(title), "")):
        query = (f"<ns1:strTitle>{html.escape(t)}</ns1:strTitle><ns1:strArtistName>{html.escape(a)}</ns1:strArtistName>"
                 "<ns1:nCurPage>0</ns1:nCurPage>")
        found = _alsong("GetResembleLyric2", query)
        if found:
            return found
    return None


# ---- Bugs (eztag metadata/bugs_lyrics.py) ----
BUGS_SEARCH = "https://music.bugs.co.kr/search/track?q={q}"
BUGS_LYRICS = "http://api.bugs.co.kr/3/tracks/{id}/lyrics?&api_key=b2de0fbe3380408bace96a5d1a76f800"


def bugs(title: str, artist: str) -> str | None:
    page = _get(BUGS_SEARCH.format(q=urllib.parse.quote(f"{artist} {title}")), {"Referer": "https://music.bugs.co.kr/"})
    rows = BeautifulSoup(page.decode("utf-8", "replace"), "html.parser").select("table.trackList tbody tr")
    want_t, want_a = _norm(_clean_title(title)), _norm(artist)

    def text(tr, sel: str) -> str:
        el = tr.select_one(sel)
        return _norm(el.get_text(strip=True)) if el else ""

    track_id = None
    for tr in rows:  # same title, and the artist when it can be told
        if _norm(_clean_title(text(tr, "p.title a"))) == want_t:
            a = text(tr, "p.artist a")
            if track_id is None or (want_a and (want_a in a or a in want_a)):
                track_id = tr.get("trackid")
                if want_a and (want_a in a or a in want_a):
                    break
    if not track_id:
        return None
    data = json.loads(_get(BUGS_LYRICS.format(id=track_id)))
    raw = ((data or {}).get("result") or {}).get("lyrics") or ""
    if "|" not in raw:  # plain lyrics only
        return raw.strip() or None
    lines = []
    for line in raw.replace("＃", "\n").split("\n"):
        sec, _, words = line.rpartition("|")
        try:
            t = float(sec)
        except ValueError:
            continue
        lines.append(f"[{int(t) // 60:02d}:{t % 60:05.2f}]{words}")
    return "\n".join(lines) or None


# ---- LRCLIB (open lyrics database; eztag metadata/lrclib.py) ----
def lrclib(title: str, artist: str, album: str, length: float | None) -> str | None:
    params = urllib.parse.urlencode({"track_name": _clean_title(title), "artist_name": artist, **({"album_name": album} if album else {})})
    items = json.loads(_get(f"https://lrclib.net/api/search?{params}", {"Accept": "application/json"})) or []
    want_t, want_a = _norm(_clean_title(title)), _norm(artist)

    def score(item: dict) -> tuple:
        a = _norm(item.get("artistName") or "")
        return (
            _norm(_clean_title(item.get("trackName") or "")) == want_t,
            bool(want_a) and (want_a in a or a in want_a),
            length is not None and abs((item.get("duration") or 0) - length) <= 3,
        )

    best = sorted((i for i in items if not i.get("instrumental") and (i.get("syncedLyrics") or i.get("plainLyrics"))), key=score, reverse=True)
    if not best or not score(best[0])[0]:
        return None
    return best[0].get("syncedLyrics") or best[0].get("plainLyrics")


# ---- the lookup ----
def _lookup(path: Path, track: Track, album: str) -> tuple[str | None, str | None]:
    """(lyrics text, where from). Synced lyrics from any source beat plain ones."""
    artist = _first_artist(track.artist_text)
    sources = [
        ("alsong", lambda: alsong_by_file(path)),
        ("bugs", lambda: bugs(track.title, artist)),
        ("lrclib", lambda: lrclib(track.title, artist, album, track.duration)),
        ("alsong", lambda: alsong_by_name(track.title, artist)),
    ]
    plain: tuple[str | None, str | None] = (None, None)
    for name, find in sources:
        try:
            text = find()
        except Exception as exc:  # noqa: BLE001 - a site down or changed: try the next one
            log.info("lyrics from %s failed for %d: %s", name, track.id, exc)
            continue
        if not text:
            continue
        if parse(text)["synced"]:
            return text[:200_000], name
        plain = plain if plain[0] else (text[:200_000], name)
    return plain


def fetched(db: Session, track: Track, path: Path, album: str) -> dict | None:
    """Lyrics fetched for the song: from the database, or looked up now (once; again after
    RETRY_DAYS when nothing was found). None when there are none."""
    row = db.get(FetchedLyrics, track.id)
    fresh = row is not None and (row.lrc or row.fetched_at > datetime.now(UTC) - timedelta(days=RETRY_DAYS))
    if not fresh:
        with _busy_lock:
            if track.id in _busy:  # another request is looking it up: don't ask the sites twice
                return None
            _busy.add(track.id)
        if not _slots.acquire(blocking=False):
            with _busy_lock:
                _busy.discard(track.id)
            return None
        try:
            db.commit()  # the lookup takes seconds: don't hold a pool connection meanwhile
            try:
                text, source = _lookup(path, track, album)
            finally:
                _slots.release()
            row = row or FetchedLyrics(track_id=track.id)
            row.lrc, row.source, row.fetched_at = text, source, datetime.now(UTC)
            db.merge(row)
            db.commit()
        finally:
            with _busy_lock:
                _busy.discard(track.id)
    return parse(row.lrc) if row and row.lrc else None
