"""Converting songs for playback: a lower bitrate for mobile data, formats browsers can't play
(WMA, APE), and volume levelling done on the server (iPhone, where the page can't change it).

Needs ffmpeg with the LAME encoder: the image has one, FFMPEG_PATH points to another. Without it
songs are sent as they are.

The output is constant-bitrate MP3: every browser plays it, also while it is still being
written, and its length and every position follow from the file size. Converted files are kept
in DATA_DIR/transcode up to TRANSCODE_CACHE_MB (least recently played out), so a second play,
seeking and the songs fetched ahead are plain files with byte ranges.

A request for a song from its start gets the file while ffmpeg writes it: playback starts at
once, but the length isn't known yet, so it can't be sought in. A request for a later position,
or one marked whole=1 (the player seeking), waits for the finished file. At most two conversions run at once
(a NAS has few cores); one nobody is waiting for any more is stopped.
"""

import asyncio
import functools
import logging
import math
import os
import shutil
import subprocess
import threading
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi.responses import FileResponse, StreamingResponse

from .config import settings

log = logging.getLogger(__name__)

QUALITIES = ("orig", "320", "256", "192", "128")
RATES = (128, 192, 256, 320)
# browsers play these as they are: only sent converted for a lower bitrate
PLAYABLE_LOSSY = {"mp3", "m4a", "mp4", "aac", "ogg", "oga", "opus"}
# no browser plays these: always converted
UNPLAYABLE = {"wma", "ape"}
SLOTS = 2
ABANDON_AFTER = 3.0  # seconds without anyone reading before an unfinished conversion is stopped
CACHE_HEADERS = {"Cache-Control": "private, max-age=3600"}


@functools.cache
def ffmpeg() -> str | None:
    """The ffmpeg to use, or None when there is none that can write MP3."""
    exe = shutil.which(settings.ffmpeg_path)
    if exe:
        try:
            out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15).stdout
            if "libmp3lame" in out:
                return exe
            log.warning("%s has no MP3 encoder (libmp3lame): songs are sent as they are", exe)
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("ffmpeg at %s doesn't run (%s): songs are sent as they are", exe, e)
    else:
        log.warning("ffmpeg not found (%s): songs are sent as they are", settings.ffmpeg_path)
    return None


def available() -> bool:
    return ffmpeg() is not None


def level_gain(rg: tuple[float | None, float | None, float | None, float | None], level: str) -> float:
    """The ReplayGain to apply in dB (track or album gain, never pushing the peak past full scale),
    rounded to 0.1 dB; 0 when levelling is off or the song has no ReplayGain tags. The same rule
    as the player's levelFor()."""
    if level == "off":
        return 0.0
    tg, tp, ag, ap = rg
    gain, peak = (ag, ap) if level == "album" and ag is not None else (tg, tp) if tg is not None else (ag, ap)
    if gain is None:
        return 0.0
    if peak and peak > 0:
        gain = min(gain, -20 * math.log10(peak))
    return round(gain, 1)


def target_kbps(fmt: str, bitrate: int | None, quality: str, gain: float) -> int | None:
    """The MP3 bitrate to convert to, or None to send the file as it is."""
    if fmt not in UNPLAYABLE and not gain:
        if quality == "orig":
            return None
        if fmt in PLAYABLE_LOSSY and bitrate and bitrate <= int(quality) + 8:  # already that small
            return None
    kbps = 320 if quality == "orig" else int(quality)
    if bitrate and fmt in PLAYABLE_LOSSY | {"wma"}:
        # a lossy source gains nothing from more bits than it has
        kbps = min(kbps, next((r for r in RATES if r >= bitrate), 320))
    return kbps


class Job:
    """One conversion into `part`, renamed to `dest` when it finishes."""

    def __init__(self, dest: Path):
        self.dest = dest
        self.part = dest.with_name(dest.name + ".part")
        self.done = threading.Event()
        self.ok = False
        self.readers = 0
        self.cancelled = False
        self.proc: subprocess.Popen | None = None


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_slots = threading.Semaphore(SLOTS)
_ready = False


def _cache_dir() -> Path:
    global _ready
    d = settings.data_dir / "transcode"
    if not _ready:
        d.mkdir(parents=True, exist_ok=True)
        for p in d.glob("*.part"):  # left by a restart in the middle of a conversion
            p.unlink(missing_ok=True)
        _ready = True
    return d


def _join(job: Job):
    job.readers += 1  # under _lock


def _leave(job: Job):
    with _lock:
        job.readers -= 1
        if job.readers > 0 or job.done.is_set():
            return
    # the player often comes straight back (a seek reloads the song): stop only if nobody did
    threading.Timer(ABANDON_AFTER, _abandon, (job,)).start()


def _abandon(job: Job):
    with _lock:
        if job.readers > 0 or job.done.is_set():
            return
        job.cancelled = True
        _jobs.pop(job.dest.name, None)
        proc = job.proc
    if proc and proc.poll() is None:
        proc.kill()


def _run(job: Job, args: list[str]):
    try:
        with _slots:
            with _lock:
                if job.cancelled:
                    return
                job.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            _, err = job.proc.communicate()
        if job.proc.returncode == 0 and not job.cancelled:
            os.replace(job.part, job.dest)
            job.ok = True
        elif not job.cancelled:
            log.warning("converting %s failed: %s", job.dest.name, err.decode(errors="replace").strip()[-500:])
    except OSError as e:
        log.warning("converting %s failed: %s", job.dest.name, e)
    finally:
        if not job.ok:
            job.part.unlink(missing_ok=True)
        with _lock:
            if _jobs.get(job.dest.name) is job:
                del _jobs[job.dest.name]
        job.done.set()
    if job.ok:
        _evict()


def _evict():
    files = []
    for p in _cache_dir().glob("*.mp3"):
        try:
            st = p.stat()
        except OSError:
            continue
        files.append((st.st_mtime, st.st_size, p))
    total = sum(f[1] for f in files)
    limit = settings.transcode_cache_mb * 1024 * 1024
    for _, size, p in sorted(files):
        if total <= limit:
            break
        p.unlink(missing_ok=True)
        total -= size


async def _follow(job: Job) -> AsyncIterator[bytes]:
    """The converted bytes as ffmpeg writes them, until it is done. Async so that a closed
    connection ends it (the reads are of a local file, short)."""
    f = None
    try:
        while f is None:
            try:
                f = open(job.part, "rb")
            except FileNotFoundError:
                if job.done.is_set():
                    if not job.ok:
                        return
                    f = open(job.dest, "rb")
                else:
                    await asyncio.sleep(0.05)
        while True:
            chunk = f.read(256 * 1024)
            if chunk:
                yield chunk
            elif job.done.is_set():
                rest = f.read()
                if rest:
                    yield rest
                return
            else:
                await asyncio.sleep(0.05)
    finally:
        if f:
            f.close()
        _leave(job)


def respond(src: str, ident: str, kbps: int, gain: float, follow: bool):
    """The converted song. `ident` names the source file as it is now (track id, size, mtime).
    follow: while it is being converted, send it as it is written instead of waiting for it."""
    dest = _cache_dir() / f"{ident}-{kbps}k{gain:+.1f}.mp3"
    if dest.is_file():
        try:
            os.utime(dest)  # recently played: kept longer
        except OSError:
            pass
        return FileResponse(dest, media_type="audio/mpeg", headers=CACHE_HEADERS)
    with _lock:
        job = _jobs.get(dest.name)
        if job is None:
            job = _jobs[dest.name] = Job(dest)
            args = [
                ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-i", src,
                "-map", "0:a:0", "-map_metadata", "-1", "-ac", "2",
                *(["-af", f"volume={gain}dB"] if gain else []),
                "-c:a", "libmp3lame", "-b:a", f"{kbps}k", "-write_xing", "0", "-id3v2_version", "0",
                "-f", "mp3", "-y", str(job.part),
            ]
            threading.Thread(target=_run, args=(job, args), daemon=True).start()
        _join(job)
    if follow:  # length unknown, so not kept by the browser
        return StreamingResponse(_follow(job), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
    try:
        job.done.wait(timeout=600)
    finally:
        _leave(job)
    if job.ok and dest.is_file():
        return FileResponse(dest, media_type="audio/mpeg", headers=CACHE_HEADERS)
    return None
