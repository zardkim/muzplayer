"""Thumbnails of the music videos on the NAS (library/video): a JPEG 640 px wide in
<data>/video-thumbs/<video id>.jpg, made once, when the video is registered (or the first time it is
asked for, for videos registered before). A picture next to the file (Clip.jpg/.png/.webp beside
Clip.mp4) is used when there is one; else ffmpeg takes a frame a little way in (10% of the video,
between 2 s and 60 s). The video's length is read on the way and kept (videos.duration).
"""

import logging
import re
import subprocess
import threading
from pathlib import Path

from PIL import Image

from . import transcode
from .config import settings
from .db import SessionLocal
from .models import Video

log = logging.getLogger(__name__)

WIDTH = 640
PICTURES = (".jpg", ".jpeg", ".png", ".webp")
DURATION = re.compile(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)")
_busy = threading.BoundedSemaphore(2)  # a NAS CPU: two at a time at most
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def thumb_dir() -> Path:
    return settings.data_dir / "video-thumbs"


def thumb_file(video_id: int) -> Path:
    return thumb_dir() / f"{video_id}.jpg"


def _failed_file(video_id: int) -> Path:
    return thumb_dir() / f"{video_id}.none"  # made nothing: don't try on every look


def remove(video_id: int) -> None:
    for path in (thumb_file(video_id), _failed_file(video_id)):
        path.unlink(missing_ok=True)


def _beside(video: Path) -> Path | None:
    """Clip.jpg (any case) next to Clip.mp4."""
    want = {(video.stem + ext).casefold() for ext in PICTURES}
    try:
        return next((p for p in video.parent.iterdir() if p.name.casefold() in want and p.is_file()), None)
    except OSError:
        return None


def _from_picture(picture: Path, out: Path) -> bool:
    try:
        with Image.open(picture) as im:
            im = im.convert("RGB")
            if im.width > WIDTH:
                im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
            im.save(out, "JPEG", quality=85)
        return True
    except (OSError, ValueError) as exc:
        log.info("video thumbnail from %s failed: %s", picture, exc)
        return False


def _duration(exe: str, video: Path) -> float | None:
    """The length ffmpeg reports (there is no ffprobe in the image)."""
    try:
        err = subprocess.run([exe, "-hide_banner", "-nostdin", "-i", str(video)], capture_output=True, text=True,
                             timeout=30).stderr
    except (OSError, subprocess.SubprocessError):
        return None
    m = DURATION.search(err)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def _frame(exe: str, video: Path, at: float, out: Path) -> bool:
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", f"{at:.2f}", "-i", str(video),
           "-frames:v", "1", "-an", "-vf", f"scale={WIDTH}:-2,format=yuvj420p", "-q:v", "4", "-f", "image2", "-y", str(out)]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.is_file() and out.stat().st_size > 0


def _make(video_id: int, video: Path) -> tuple[bool, float | None]:
    out = thumb_file(video_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.jpg")
    exe = transcode.ffmpeg()
    seconds = _duration(exe, video) if exe else None
    made = False
    picture = _beside(video)
    if picture is not None:
        made = _from_picture(picture, tmp)
    if not made and exe:
        at = min(60.0, max(2.0, seconds * 0.1)) if seconds else 2.0
        if seconds is not None and at >= seconds:
            at = 0.0
        made = _frame(exe, video, at, tmp) or (at > 0 and _frame(exe, video, 0.0, tmp))  # short videos: the start
    if made:
        tmp.replace(out)
    else:
        tmp.unlink(missing_ok=True)
        _failed_file(video_id).touch()
        log.info("no thumbnail for video %d (%s)", video_id, video)
    return made, seconds


def ensure(video_id: int, video: Path) -> Path | None:
    """The thumbnail, made now if needed (the caller waits). None when none can be made."""
    out = thumb_file(video_id)
    if out.is_file():
        return out
    if _failed_file(video_id).exists():
        return None
    with _locks_guard:
        lock = _locks.setdefault(video_id, threading.Lock())
    with lock, _busy:
        if out.is_file():
            return out
        if _failed_file(video_id).exists():
            return None
        made, seconds = _make(video_id, video)
    if seconds is not None:
        with SessionLocal() as db:
            row = db.get(Video, video_id)
            if row is not None and row.duration is None:
                row.duration = round(seconds)
                db.commit()
    return out if made else None


def make_later(video_id: int, video: Path) -> None:
    """Right after registering: made in the background, so adding a folder of videos stays quick."""
    threading.Thread(target=ensure, args=(video_id, video), daemon=True, name="video-thumb").start()
