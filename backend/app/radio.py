"""Korean radio, live: the stations radio.bsod.kr lists, played through this server (the big
broadcasters' streams asked of the broadcasters themselves: DIRECT).

radio.bsod.kr gives each station a fixed address (/stream?stn=kbs&ch=1radio) that redirects to the
broadcaster's stream of the moment, often with a one-time token. Browsers can't use those streams
directly in many cases (plain http on an https page, broadcasters without CORS, HLS that only Safari
plays), so the server relays each one as a single stream any <audio> plays, in the background on a
phone too:

  - a plain audio stream (Icecast/Shoutcast MP3 or AAC) is passed on as it comes;
  - HLS (most stations): the server follows the playlist, fetches the new segments as they appear
    (TS, AAC or fragmented MP4) and pipes them into ffmpeg, which sends out MP3.

The station list (radio_stations.json) was taken from the site and each stream checked to play;
the stream addresses themselves are asked for again every time a station starts. Anyone may add
stations of their own by address (models.RadioCustom, "c<id>"): a radio.bsod.kr one, a plain stream,
HLS, or a .pls/.m3u playlist naming one (checked by probe when added).
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import weakref
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import transcode

log = logging.getLogger(__name__)

SOURCE = "https://radio.bsod.kr/stream"
STATIONS: list[dict] = json.loads((Path(__file__).parent / "radio_stations.json").read_text("utf-8"))
BY_ID = {s["id"]: s for s in STATIONS}
REGIONS = ("seoul", "busan", "daegu", "gwangju", "jeonbuk", "daejeon", "chungbuk", "gangwon", "jeju")
MAX_RELAYS = 6  # listeners at once (each HLS one runs an ffmpeg)
TIMEOUT = 10
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_slots = threading.BoundedSemaphore(MAX_RELAYS)


class Unavailable(Exception):
    """The station's stream can't be had now (the site or the broadcaster didn't answer)."""


class Busy(Exception):
    """Too many stations playing at once."""


class _Lease:
    """One of the MAX_RELAYS slots, given back exactly once with whatever else the relay holds.

    Given back without awaiting anything: when the listener leaves, the stream's task is cancelled
    and an await in its cleanup would be cancelled too (the slot was never given back, and after six
    station changes every station answered 429). Also given back if the response never started.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._done = False
        self.cleanup = None

    def release(self) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        try:
            if self.cleanup:
                self.cleanup()
        finally:
            _slots.release()


def _end_ffmpeg(proc: subprocess.Popen, stop: threading.Event) -> None:
    stop.set()
    proc.kill()
    threading.Thread(target=proc.wait, daemon=True, name="radio-reap").start()  # no zombie


def _open(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=TIMEOUT)


# ---- the broadcasters' own live addresses (checked 2026-11-12) ----
# radio.bsod.kr answers this server 403 (Cloudflare) since November 2026. Most stations' streams are
# at a fixed address ("stream" in radio_stations.json, the broadcasters' own: the addresses that
# site's templates list, github.com/BSofDeath/radio.bsod.kr); a few are asked for each time (DIRECT:
# an address with a token, or one that changes by date or server). radio.bsod.kr is left for the rest.
HLS = "application/vnd.apple.mpegurl"
KST = timezone(timedelta(hours=9))


def _kbs(channel: str) -> str:
    """KBS: the channel's 128 kbps HLS (its web player's own API; the address carries a policy token).
    A regional station's channel is "<station code>_<channel>" (10_21: KBS부산 1라디오)."""
    with _open(f"https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/{channel}") as resp:
        items = json.load(resp).get("channel_item") or []
    return next(i["service_url"] for i in items if i.get("media_type") in ("radio", "local") and i.get("service_url"))


def _text(url: str) -> str:
    """MBC, SBS: the live address (with a token) as the whole answer."""
    with _open(url) as resp:
        return resp.read(4000).decode("utf-8", "replace").strip()


def _busan_mbc(kind: str) -> str:
    """부산MBC: an address with today's date (KST) in a letter code."""
    code = "".join("qhsagbjcpd"[int(c)] for c in datetime.now(KST).strftime("%y%m%d"))
    return f"https://brook.bsmbc.com/live/BusanMBC_{kind}_onairstream.{code}/playlist.m3u8"


def _afn(mount: str) -> str:
    """AFN: one of streamtheworld's servers of the moment."""
    with _open(f"https://playerservices.streamtheworld.com/api/livestream?station={mount}&transports=http%2Chls&version=1.10") as resp:
        hosts = re.findall(r"<ip>(.*?)</ip>", resp.read(200_000).decode("utf-8", "replace"))
    return f"https://{hosts[-1]}/{mount}AAC.aac"


_MBC = "https://sminiplay.imbc.com/aacplay.ashx?agent=webapp&channel={}"
_SBS = "https://apis.sbs.co.kr/play-api/1.0/livestream/{}?protocol=hls&ssl=Y"
_KBS_CHANNELS = {"1radio": "21", "2radio": "22", "3radio": "23", "1fm": "24", "2fm": "25", "hanminjok": "26"}
_KBS_LOCAL = {  # KBS's regional station codes
    "busan": "10", "ulsan": "11", "changwon": "20", "jinju": "21", "daegu": "30", "andong": "31", "pohang": "32",
    "gwangju": "40", "mokpo": "41", "suncheon": "43", "jeonju": "50", "daejeon": "60", "cheongju": "70",
    "chungju": "71", "chuncheon": "80", "gangneung": "81", "wonju": "82", "jeju": "90",
}
DIRECT = {
    "mbc-sfm": lambda: _text(_MBC.format("sfm")), "mbc-fm4u": lambda: _text(_MBC.format("mfm")),
    "mbc-chm": lambda: _text(_MBC.format("chm")),
    "mbc-sfm-busan": lambda: _busan_mbc("AM"), "mbc-fm4u-busan": lambda: _busan_mbc("FM"),
    "sbs-powerfm": lambda: _text(_SBS.format("powerpc/powerfm")), "sbs-lovefm": lambda: _text(_SBS.format("lovepc/lovefm")),
    "sbs-dmb": lambda: _text(_SBS.format("sbsdmbpc/sbsdmb")),
    "afn-humphreys": lambda: _afn("AFNP_OSN"), "afn-kunsan": lambda: _afn("AFNP_KSN"),
}


def _kbs_of(station_id: str) -> str | None:
    """"kbs-1fm-busan" -> "10_24", "kbs-2fm" -> "25"."""
    parts = station_id.split("-")
    if parts[0] != "kbs" or len(parts) < 2 or parts[1] not in _KBS_CHANNELS:
        return None
    if len(parts) == 2:
        return _KBS_CHANNELS[parts[1]]
    local = _KBS_LOCAL.get(parts[2])
    return f"{local}_{_KBS_CHANNELS[parts[1]]}" if local else None


def _direct(station: dict) -> str | None:
    sid = station.get("id", "")
    ask = DIRECT.get(sid)
    if ask is None and (kbs := _kbs_of(sid)):
        ask = lambda: _kbs(kbs)  # noqa: E731
    if ask is None:
        return None
    try:
        url = ask()
    except Exception as exc:  # noqa: BLE001 - the broadcaster's API moved or failed: the next way then
        log.info("radio %s: the broadcaster's address: %s", sid, exc)
        return None
    return url if url.startswith("https://") else None


def resolve(station: dict) -> tuple[str, str]:
    """(the stream's address now, its content type): asked of the broadcaster (DIRECT), its fixed
    address ("stream"; one's own station's "url"), else radio.bsod.kr's address for it."""
    if direct := _direct(station):
        return direct, HLS if ".m3u8" in direct else "audio/aac"
    url = station.get("stream") or station.get("url") or SOURCE + "?" + urllib.parse.urlencode(station["q"])
    if station.get("stream") and _is_hls(url, ""):
        return url, HLS
    try:
        with _open(url) as resp:
            return resp.geturl(), resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise Unavailable(str(exc)) from exc


def _is_hls(url: str, ctype: str) -> bool:
    return "mpegurl" in ctype or urllib.parse.urlparse(url).path.lower().endswith(".m3u8")


# ---- HLS: follow the playlist, feed the new segments to ffmpeg ----
_ATTR_URI = re.compile(r'URI="([^"]+)"')


def _playlist(url: str) -> tuple[str, str]:
    with _open(url) as resp:
        return resp.geturl(), resp.read(1_000_000).decode("utf-8", "replace")


def _feed(station: dict, first_url: str, out, stop: threading.Event) -> None:
    """Writes the station's audio segments, in order, to `out` until stopped. The playlist address
    is asked for again when it stops answering (tokens run out)."""
    media = first_url
    seen: list[str] = []  # segment addresses already sent (without their query: tokens change)
    sent_init = False
    try:
        while not stop.is_set():
            try:
                base, text = _playlist(media)
            except (urllib.error.URLError, OSError):
                media, _ = resolve(station)  # raises Unavailable when the site has nothing either
                continue
            if "#EXT-X-STREAM-INF" in text:  # a list of variants: take the first
                media = urllib.parse.urljoin(base, next(l for l in text.splitlines() if l and not l.startswith("#")))
                continue
            target = 6.0
            if m := re.search(r"#EXT-X-TARGETDURATION:(\d+(?:\.\d+)?)", text):
                target = float(m.group(1))
            if not sent_init and (m := re.search(r"#EXT-X-MAP:[^\n]*", text)) and (uri := _ATTR_URI.search(m.group(0))):
                with _open(urllib.parse.urljoin(base, uri.group(1))) as resp:
                    out.write(resp.read())
                sent_init = True
            segments = [urllib.parse.urljoin(base, l) for l in text.splitlines() if l and not l.startswith("#")]
            if not seen:
                segments = segments[-3:]  # start near the live edge, not minutes back
            for seg in segments:
                key = seg.split("?")[0]
                if key in seen or stop.is_set():
                    continue
                with _open(seg) as resp:
                    out.write(resp.read())
                out.flush()
                seen.append(key)
            del seen[:-200]
            media = base
            stop.wait(max(1.0, target / 2))
    except (BrokenPipeError, ValueError, Unavailable):
        pass  # the listener left (ffmpeg's input closed), or the station went away
    except Exception:  # noqa: BLE001 - a station that misbehaves: end its stream, keep the server
        log.exception("radio %s stopped", station["id"])
    finally:
        try:
            out.close()
        except OSError:
            pass


async def relay(station: dict) -> tuple[AsyncIterator[bytes], str]:
    """(the station's audio, its content type) for a StreamingResponse. Raises Unavailable or Busy."""
    if not _slots.acquire(blocking=False):
        raise Busy
    lease = _Lease()
    try:
        url, ctype = await asyncio.to_thread(resolve, station)
    except BaseException:
        lease.release()
        raise
    if not _is_hls(url, ctype):
        body = _passthrough(url, lease)
        weakref.finalize(body, lease.release)
        return body, ("audio/aac" if "aac" in ctype else ctype or "audio/mpeg")
    exe = transcode.ffmpeg()
    if exe is None:
        lease.release()
        raise Unavailable("no ffmpeg")
    proc = subprocess.Popen(
        [exe, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-vn",
         "-c:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", "pipe:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    stop = threading.Event()
    lease.cleanup = lambda: _end_ffmpeg(proc, stop)
    threading.Thread(target=_feed, args=(station, url, proc.stdin, stop), daemon=True, name="radio-feed").start()
    body = _from_ffmpeg(proc, lease)
    weakref.finalize(body, lease.release)
    return body, "audio/mpeg"


async def _from_ffmpeg(proc: subprocess.Popen, lease: _Lease) -> AsyncIterator[bytes]:
    fd = proc.stdout.fileno()
    try:
        while True:
            chunk = await asyncio.to_thread(os.read, fd, 16384)
            if not chunk:
                return
            yield chunk
    finally:  # the listener left (or the station ended): stop fetching and ffmpeg
        lease.release()


async def _passthrough(url: str, lease: _Lease) -> AsyncIterator[bytes]:
    resp = None
    try:
        resp = await asyncio.to_thread(_open, url)
        last = time.monotonic()
        while True:
            chunk = await asyncio.to_thread(resp.read1, 16384)
            if not chunk:
                if time.monotonic() - last > TIMEOUT:
                    return
                continue
            last = time.monotonic()
            yield chunk
    except (urllib.error.URLError, OSError):
        return
    finally:
        if resp is not None:
            resp.close()
        lease.release()


def station_out(s: dict) -> dict:
    out = {"id": s["id"], "name": s["name"], "stn": s["stn"], "regions": s["regions"], "logo": s.get("logo")}
    if s.get("freq"):
        out["freq"] = s["freq"]  # by region: "FM 89.1" | "AM 972" (the Radio page's tuner)
    if s.get("custom"):
        out.update(custom=True, url=s["url"])
    return out


def custom_station(row) -> dict:
    """A station someone added (models.RadioCustom), as the listed ones are."""
    return {"id": f"c{row.id}", "name": row.name, "stn": "custom", "regions": ["custom"], "logo": None, "url": row.url, "custom": True}


class Unsupported(Exception):
    """The address isn't a stream this server can play."""


_AUDIO = ("audio/", "application/ogg", "application/octet-stream", "video/mp2t")
_PLAYLIST_URL = re.compile(r"^(?:File\d+=)?\s*(https?://\S+)", re.M | re.I)


def probe(url: str, depth: int = 0) -> str:
    """The address to keep for a station added by hand: the stream itself, or the one a .pls/.m3u
    playlist names. Raises Unsupported (not a stream) or Unavailable (it didn't answer)."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise Unsupported
    try:
        with _open(url) as resp:
            final, ctype = resp.geturl(), resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            path = urllib.parse.urlparse(final).path.lower()
            listed = "scpls" in ctype or "mpegurl" in ctype or path.endswith((".pls", ".m3u", ".m3u8"))
            head = resp.read(65536).decode("utf-8", "replace") if listed else ""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise Unavailable(str(exc)) from exc
    if listed:
        if "#EXT-X-" in head:
            return url  # HLS
        m = _PLAYLIST_URL.search(head)
        if m and depth < 2:
            return probe(m.group(1), depth + 1)  # a playlist that names the stream
        raise Unsupported
    if ctype.startswith(_AUDIO) or "aac" in ctype or "mpeg" in ctype:
        return url
    raise Unsupported
