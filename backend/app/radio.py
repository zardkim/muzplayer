"""Korean radio, live: the stations radio.bsod.kr lists, played through this server.

radio.bsod.kr gives each station a fixed address (/stream?stn=kbs&ch=1radio) that redirects to the
broadcaster's stream of the moment, often with a one-time token. Browsers can't use those streams
directly in many cases (plain http on an https page, broadcasters without CORS, HLS that only Safari
plays), so the server relays each one as a single stream any <audio> plays, in the background on a
phone too:

  - a plain audio stream (Icecast/Shoutcast MP3 or AAC) is passed on as it comes;
  - HLS (most stations): the server follows the playlist, fetches the new segments as they appear
    (TS, AAC or fragmented MP4) and pipes them into ffmpeg, which sends out MP3.

The station list (radio_stations.json) was taken from the site and each stream checked to play;
the stream addresses themselves are asked for again every time a station starts.
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
from collections.abc import AsyncIterator
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


def _open(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=TIMEOUT)


def resolve(station: dict) -> tuple[str, str]:
    """(the stream's address now, its content type), from the station's fixed address."""
    url = SOURCE + "?" + urllib.parse.urlencode(station["q"])
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
    try:
        url, ctype = await asyncio.to_thread(resolve, station)
    except BaseException:
        _slots.release()
        raise
    if not _is_hls(url, ctype):
        return _passthrough(url), ("audio/aac" if "aac" in ctype else ctype or "audio/mpeg")
    exe = transcode.ffmpeg()
    if exe is None:
        _slots.release()
        raise Unavailable("no ffmpeg")
    proc = subprocess.Popen(
        [exe, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-vn",
         "-c:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", "pipe:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    stop = threading.Event()
    threading.Thread(target=_feed, args=(station, url, proc.stdin, stop), daemon=True, name="radio-feed").start()
    return _from_ffmpeg(proc, stop), "audio/mpeg"


async def _from_ffmpeg(proc: subprocess.Popen, stop: threading.Event) -> AsyncIterator[bytes]:
    fd = proc.stdout.fileno()
    try:
        while True:
            chunk = await asyncio.to_thread(os.read, fd, 16384)
            if not chunk:
                return
            yield chunk
    finally:  # the listener left (or the station ended): stop fetching and ffmpeg
        stop.set()
        proc.kill()
        await asyncio.to_thread(proc.wait)
        _slots.release()


async def _passthrough(url: str) -> AsyncIterator[bytes]:
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
        _slots.release()


def station_out(s: dict) -> dict:
    return {"id": s["id"], "name": s["name"], "stn": s["stn"], "regions": s["regions"]}
