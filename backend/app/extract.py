"""Audio taken out of music videos (docs/extract_plan.md): a YouTube video's sound through yt-dlp
(audio only), or a NAS video file's through ffmpeg, made an m4a (AAC kept as it is when it is AAC)
or an mp3, with tags and a cover written into the file, saved in the extraction folder and scanned
into the library as the "extracted" kind.

The extraction folder (settings.extract_dir) is a folder of the music library mounted writable; the
rest of the library stays read-only, and nothing is written anywhere else. YouTube needs yt-dlp and
a JavaScript runtime (deno, in the image) and is off until an admin turns it on (appconf
extract_youtube: YouTube's terms allow downloads only where it permits them).

The tags (this step): the song the video is linked to when it is, else the video title read as
"Artist - Title" ([MV], (Official Video)... left out) with the channel as the artist when there's no
dash. The cover is the video's thumbnail cut square (the linked album's only when there is none).
Saved as cover music/<artist>/<disc>-<track> <title>.m4a (eztag's "%disc%-%track% %title%"). Nothing is made
up: what isn't known is left empty. Jobs run one at a time in the background (ExtractJob).
"""

import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from . import appconf, transcode
from .config import settings
from .db import SessionLocal
from .models import Album, Artist, ExtractJob, Genre, LibraryFolder, ScanJob, Track, TrackGenre, Video

log = logging.getLogger(__name__)

FORMATS = ("m4a", "mp3")
MP3_RATE = "320k"
AAC_RATE = "256k"  # an m4a from a source that isn't AAC (YouTube's Opus)
COVER_PX = 1000
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_lock = threading.Lock()  # held while a job runs (backup.restore waits for none)
_wake = threading.Event()
_started = False


class ExtractError(Exception):
    """Carries only a code for the frontend."""


# ---- what this server can do ----
def folder_name() -> str | None:
    """The extraction folder's top-level name in the music library, or None when it isn't in it."""
    try:
        rel = settings.extract_dir.resolve().relative_to(settings.music_dir.resolve())
    except (ValueError, OSError):
        return None
    return rel.parts[0] if len(rel.parts) == 1 else None


def writable() -> bool:
    d = settings.extract_dir
    if not d.is_dir():
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=d, prefix=".w"):
            return True
    except OSError:
        return False


def ytdlp_version() -> str | None:
    try:
        from yt_dlp.version import __version__

        return __version__
    except ImportError:
        return None


def deno() -> str | None:
    return shutil.which(settings.deno_path)


def status() -> dict:
    return {
        "folder": str(settings.extract_dir), "folder_ok": writable() and folder_name() is not None,
        "ytdlp": ytdlp_version(), "deno": bool(deno()), "ffmpeg": bool(transcode.ffmpeg()),
        "youtube": appconf.get("extract_youtube") == "on", "format": appconf.get("extract_format") or "m4a",
    }


# ---- the queue ----
def enqueue(db, video: Video, user_id: int, fmt: str) -> ExtractJob:
    if fmt not in FORMATS:
        raise ExtractError("extract_format")
    if not writable() or folder_name() is None:
        raise ExtractError("extract_folder")
    if video.youtube_id:
        if appconf.get("extract_youtube") != "on":
            raise ExtractError("extract_youtube_off")
        if not ytdlp_version():
            raise ExtractError("extract_no_ytdlp")
    elif not video.file_path:
        raise ExtractError("extract_source")
    job = ExtractJob(video_id=video.id, user_id=user_id, format=fmt, title=video.title)
    db.add(job)
    db.commit()
    start_worker()
    _wake.set()
    return job


def start_worker() -> None:
    """The background worker (once): jobs one after another; interrupted ones (a restart) failed."""
    global _started
    if _started:
        return
    _started = True
    with SessionLocal() as db:
        if settings.extract_dir.is_dir():
            ensure_folder_kind(db)  # songs already there (a restore, files put in by hand) list as extracted too
        for job in db.scalars(select(ExtractJob).where(ExtractJob.status == "running")):
            job.status, job.error, job.finished_at = "failed", "extract_interrupted", datetime.now(UTC)
        db.commit()
    threading.Thread(target=_loop, daemon=True, name="extract").start()
    _wake.set()


def _loop() -> None:
    while True:
        _wake.wait(60)
        _wake.clear()
        while True:
            with SessionLocal() as db:
                job_id = db.scalar(select(ExtractJob.id).where(ExtractJob.status == "pending").order_by(ExtractJob.id).limit(1))
            if job_id is None:
                break
            with _lock:
                _run(job_id)


def _set(job_id: int, **values) -> None:
    with SessionLocal() as db:
        job = db.get(ExtractJob, job_id)
        if job is not None:
            for k, v in values.items():
                setattr(job, k, v)
            db.commit()


def _run(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(ExtractJob, job_id)
        video = db.get(Video, job.video_id) if job and job.video_id else None
        if job is None or job.status != "pending":
            return
        if video is None:
            job.status, job.error, job.finished_at = "failed", "extract_source", datetime.now(UTC)
            db.commit()
            return
        job.status, job.step, job.progress, job.error = "running", "download", 0, None
        db.commit()
        source = {"id": video.id, "youtube_id": video.youtube_id, "file_path": video.file_path, "title": video.title,
                  "channel": video.channel, "track_id": video.track_id, "album_id": video.album_id}
        fmt = job.format
    work = Path(tempfile.mkdtemp(prefix="extract-", dir=settings.data_dir))
    try:
        info: dict = {}
        if source["youtube_id"]:
            audio, info = _download(job_id, source["youtube_id"], work)
        else:
            audio = settings.video_dir / source["file_path"]
            if not audio.is_file():
                raise ExtractError("extract_source")
        _set(job_id, step="tags", progress=1)
        tags, cover = _tags(source, info)
        _set(job_id, step="convert")
        target = _target(tags, fmt)
        part = target.with_name(f".{target.name}.part")
        target.parent.mkdir(parents=True, exist_ok=True)
        _convert(audio, part, fmt)
        _write_tags(part, fmt, tags, cover)
        os.replace(part, target)
        rel = target.relative_to(settings.music_dir).as_posix()
        _set(job_id, step="scan", file_path=rel, found=tags | {"cover": tags.get("cover")})
        track_id = _scan(rel)
        _set(job_id, status="done", step="", track_id=track_id, finished_at=datetime.now(UTC))
        log.info("extracted %s -> %s", source["title"], rel)
    except ExtractError as exc:
        _set(job_id, status="failed", error=str(exc), finished_at=datetime.now(UTC))
    except Exception:  # noqa: BLE001
        log.exception("extract %s failed", source["title"])
        _set(job_id, status="failed", error="extract_failed", finished_at=datetime.now(UTC))
    finally:
        shutil.rmtree(work, ignore_errors=True)
        for p in settings.extract_dir.rglob(".*.part"):
            p.unlink(missing_ok=True)
        _prune_empty()


def _prune_empty() -> None:
    """Folders a failed job left empty (or with only a cover)."""
    root = settings.extract_dir
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(c.name != "cover.jpg" for c in d.iterdir()):
            shutil.rmtree(d, ignore_errors=True)


# ---- 1. the sound ----
def _download(job_id: int, youtube_id: str, work: Path) -> tuple[Path, dict]:
    """The video's best stereo AAC sound (else its best sound) through yt-dlp: (file, its info)."""
    import yt_dlp

    last = [0.0]

    def hook(d: dict) -> None:
        if d.get("status") == "downloading" and time.monotonic() - last[0] > 1:
            last[0] = time.monotonic()
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                _set(job_id, progress=min(0.99, d.get("downloaded_bytes", 0) / total))

    opts = {
        "format": "bestaudio[ext=m4a][audio_channels<=2]/bestaudio[ext=m4a]/bestaudio",
        "outtmpl": str(work / "source.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True,
        "noprogress": True, "progress_hooks": [hook], "socket_timeout": 30, "retries": 3,
    }
    if js := deno():
        opts["js_runtimes"] = {"deno": {"path": js}}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={youtube_id}", download=True)
    except yt_dlp.utils.DownloadError as exc:
        log.info("yt-dlp %s: %s", youtube_id, str(exc)[:300])
        raise ExtractError(_why(str(exc))) from None
    files = [p for p in work.iterdir() if p.name.startswith("source.")]
    if not files:
        raise ExtractError("extract_ytdlp")
    return files[0], {k: info.get(k) for k in ("id", "title", "channel", "uploader", "description", "duration", "acodec")}


def _why(message: str) -> str:
    """The code for what yt-dlp said (the region before "unavailable": its message holds both)."""
    text = message.lower()
    if "not a bot" in text or "confirm you" in text and "bot" in text:
        return "extract_bot"  # YouTube asks this server to sign in: later, or a newer yt-dlp
    if re.search(r"\b(country|countries|region|geo)\b", text):
        return "extract_geo"
    if re.search(r"\bage[- ]restricted\b|\binappropriate for some users\b|\bconfirm your age\b", text):
        return "extract_age"
    if re.search(r"\b(private|unavailable|removed|terminated|does not exist)\b", text):
        return "extract_unavailable"
    return "extract_ytdlp"


# ---- 2. tags and cover ----
_NOISE = re.compile(
    r"\s*[\[(【](?:[^\])】]*?\b(?:mv|m/v|official|music video|lyric[s]?|audio|teaser|4k|hd|live clip|performance video|special clip)\b[^\])】]*)[\])】]\s*",
    re.I,
)
_TRAILER = re.compile(r"\s*(?:\||｜|/)\s*.*$")  # "Title | Channel" or "Title / 가사"


def parse_title(title: str, channel: str) -> tuple[str, str]:
    """(artist, title) from a video title: "[MV] 아이유(IU) - 밤편지" -> ("아이유(IU)", "밤편지")."""
    t = unicodedata.normalize("NFC", title or "")
    t = _NOISE.sub(" ", t)
    t = re.sub(r"^\s*\[[^\]]*\]\s*", "", t)  # a leading [tag] of any kind ([STATION], [Special])
    t = _TRAILER.sub("", t) if " - " in t.split("|")[0] else t
    t = re.sub(r"\s+(?:official\s+)?(?:m/?v|music video|lyric video|performance video)\s*$", "", t, flags=re.I)  # a bare "Official MV" at the end
    t = " ".join(t.split()).strip(" -–")
    m = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"""^(.+?)\s*['‘’"“]([^'‘’"“”]+)['’"”]\s*(.*)$""", t)  # BTS (방탄소년단) 'Dynamite'
    if m:
        return m.group(1).strip(), " ".join(f"{m.group(2)} {m.group(3)}".split())
    artist = re.sub(r"\s*(?:-\s*Topic|VEVO|Official)$", "", channel or "", flags=re.I).strip()
    return artist, t


def _tags(source: dict, info: dict) -> tuple[dict, bytes | None]:
    """The tags to write and the cover (JPEG bytes): the linked song's, else read off the video."""
    from .scanner import cover_file

    url = f"https://www.youtube.com/watch?v={source['youtube_id']}" if source["youtube_id"] else ""
    with SessionLocal() as db:
        track = db.get(Track, source["track_id"]) if source["track_id"] else None
        album = db.get(Album, track.album_id if track and track.album_id else source["album_id"]) if (track or source["album_id"]) else None
        if track is not None:
            album_artist = db.get(Artist, album.album_artist_id) if album and album.album_artist_id else None
            genre = db.scalar(select(Genre.name).join(TrackGenre, TrackGenre.genre_id == Genre.id).where(TrackGenre.track_id == track.id).limit(1))
            tags = {
                "title": track.title, "artist": (track.artist_text or "").replace(" / ", ", "), "album": album.title if album else "",
                "album_artist": album_artist.name if album_artist else (track.artist_text or ""),
                "year": str(album.year) if album and album.year else "", "genre": genre or "", "track": track.track_no or 1,
                "disc": track.disc_no or 1, "source": "track",
            }
        else:
            artist, title = parse_title(info.get("title") or source["title"], info.get("channel") or info.get("uploader") or source["channel"])
            tags = {"title": title, "artist": artist, "album": album.title if album else title,
                    "album_artist": artist, "year": str(album.year) if album and album.year else "", "genre": "", "track": 1,
                    "disc": 1, "source": "title"}
        tags["comment"] = url
        album_cover = cover_file(album.id, "large") if album is not None and album.cover_path else None
    # the cover: the video's own picture (its thumbnail cut square); the linked album's only without one
    cover = _thumbnail(source)
    tags["cover"] = ("youtube" if source["youtube_id"] else "video") if cover else None
    if cover is None and album_cover is not None and album_cover.is_file():
        cover, tags["cover"] = album_cover.read_bytes(), "album"
    return tags, cover


def _square(data: bytes) -> bytes | None:
    """A picture cut square (black bars above and below taken off first), at most COVER_PX."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            gray = im.convert("L")
            w, h = gray.size
            top, bottom = 0, h
            while top < h // 3 and max(gray.crop((0, top, w, top + 1)).getdata()) < 24:
                top += 1
            while bottom > h - h // 3 and max(gray.crop((0, bottom - 1, w, bottom)).getdata()) < 24:
                bottom -= 1
            im = im.crop((0, top, w, bottom))
            side = min(im.size)
            left, upper = (im.width - side) // 2, (im.height - side) // 2
            im = im.crop((left, upper, left + side, upper + side))
            if side > COVER_PX:
                im = im.resize((COVER_PX, COVER_PX), Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, "JPEG", quality=90)
            return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


def _thumbnail(source: dict) -> bytes | None:
    if source["youtube_id"]:
        for size in ("maxresdefault", "sddefault", "hqdefault"):
            try:
                req = urllib.request.Request(f"https://i.ytimg.com/vi/{source['youtube_id']}/{size}.jpg", headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed host
                    if (cover := _square(resp.read(5_000_000))) is not None:
                        return cover
            except Exception:  # noqa: BLE001
                continue
        return None
    from .video_thumbs import ensure

    frame = ensure(source["id"], settings.video_dir / source["file_path"])
    return _square(frame.read_bytes()) if frame else None


# ---- 3. the file ----
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _safe(name: str, fallback: str) -> str:
    name = _UNSAFE.sub("_", unicodedata.normalize("NFC", name or "")).strip(" .")
    return name[:120] or fallback


def _target(tags: dict, fmt: str) -> Path:
    """extract_dir/<artist>/<disc>-<track> <title>.<fmt> (eztag's "%disc%-%track% %title%": the track
    two digits, the disc as it is), a number added when the name is taken."""
    folder = settings.extract_dir / _safe(tags["album_artist"] or tags["artist"], "Unknown")
    stem = f"{int(tags.get('disc') or 1)}-{int(tags.get('track') or 1):02d} {_safe(tags['title'], 'Untitled')}"
    target = folder / f"{stem}.{fmt}"
    n = 2
    while target.exists():
        target = folder / f"{stem} ({n}).{fmt}"
        n += 1
    if settings.extract_dir.resolve() not in target.resolve().parents:  # never outside the folder
        raise ExtractError("extract_folder")
    return target


def _ffmpeg(args: list[str]) -> bool:
    exe = transcode.ffmpeg()
    if exe is None:
        raise ExtractError("extract_convert")
    run = subprocess.run([exe, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args], capture_output=True, timeout=1800)
    if run.returncode:
        err = run.stderr.decode("utf-8", "replace")
        if "matches no streams" in err:
            raise ExtractError("extract_no_audio")  # a video without sound
        log.info("ffmpeg: %s", err[-400:])
    return run.returncode == 0


def _convert(src: Path, out: Path, fmt: str) -> None:
    """The sound alone, without the source's own tags: AAC kept as it is in an m4a when it is AAC."""
    base = ["-i", str(src), "-vn", "-map", "0:a:0", "-map_metadata", "-1"]
    if fmt == "m4a":
        if _ffmpeg([*base, "-c:a", "copy", "-f", "ipod", str(out)]):
            return
        if _ffmpeg([*base, "-c:a", "aac", "-b:a", AAC_RATE, "-f", "ipod", str(out)]):
            return
    elif _ffmpeg([*base, "-c:a", "libmp3lame", "-b:a", MP3_RATE, "-f", "mp3", str(out)]):
        return
    raise ExtractError("extract_convert")


def _write_tags(path: Path, fmt: str, tags: dict, cover: bytes | None) -> None:
    if fmt == "m4a":
        from mutagen.mp4 import MP4, MP4Cover

        f = MP4(path)
        f.tags = f.tags or {}
        pairs = {"\xa9nam": tags["title"], "\xa9ART": tags["artist"], "aART": tags["album_artist"], "\xa9alb": tags["album"],
                 "\xa9day": tags["year"], "\xa9gen": tags["genre"], "\xa9cmt": tags["comment"]}
        for k, v in pairs.items():
            if v:
                f.tags[k] = [v]
        f.tags["trkn"] = [(int(tags.get("track") or 1), 0)]
        f.tags["disk"] = [(int(tags.get("disc") or 1), 0)]
        if cover:
            f.tags["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
        f.save()
        return
    from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, ID3NoHeaderError

    try:
        f = ID3(path)
    except ID3NoHeaderError:
        f = ID3()
    for frame, v in ((TIT2, tags["title"]), (TPE1, tags["artist"]), (TPE2, tags["album_artist"]), (TALB, tags["album"]),
                     (TDRC, tags["year"]), (TCON, tags["genre"])):
        if v:
            f.add(frame(encoding=3, text=v))
    f.add(TRCK(encoding=3, text=str(int(tags.get("track") or 1))))
    f.add(TPOS(encoding=3, text=str(int(tags.get("disc") or 1))))
    if tags["comment"]:
        f.add(COMM(encoding=3, lang="kor", desc="", text=tags["comment"]))
    if cover:
        f.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
    f.save(path, v2_version=4)


# ---- 4. into the library ----
def ensure_folder_kind(db) -> None:
    """The extraction folder is the "extracted" kind (its songs listed apart in the library)."""
    name = folder_name()
    if name and db.get(LibraryFolder, name) is None:
        db.add(LibraryFolder(path=name, kind="extracted"))
        db.commit()


def _scan(rel: str) -> int | None:
    """Scans the extraction folder (after a scan running now) and returns the new song's id."""
    from .scanner import start_scan

    name = folder_name()
    with SessionLocal() as db:
        ensure_folder_kind(db)
        deadline = time.monotonic() + 1800
        job = None
        while job is None and time.monotonic() < deadline:
            job = start_scan(db, folder=name)
            if job is None:
                time.sleep(5)
        if job is None:
            raise ExtractError("extract_scan")
        job_id = job.id
    while time.monotonic() < deadline:
        time.sleep(1)
        with SessionLocal() as db:
            st = db.scalar(select(ScanJob.status).where(ScanJob.id == job_id))
            if st != "running":
                return db.scalar(select(Track.id).where(Track.file_path == rel))
    raise ExtractError("extract_scan")


def remove_file(rel: str) -> None:
    """Deletes an extracted song's file (only inside the extraction folder), and its folders left empty."""
    path = (settings.music_dir / rel).resolve()
    root = settings.extract_dir.resolve()
    if root not in path.parents:
        raise ExtractError("extract_folder")
    path.unlink(missing_ok=True)
    for parent in path.parents:
        if parent == root:
            break
        leftovers = [p for p in parent.iterdir() if p.name != "cover.jpg"] if parent.is_dir() else []
        if leftovers:
            break
        shutil.rmtree(parent, ignore_errors=True)
