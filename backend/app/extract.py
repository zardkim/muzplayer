"""Audio taken out of music videos (docs/extract_plan.md): a YouTube video's sound through yt-dlp
(audio only), or a NAS video file's through ffmpeg, made an m4a (AAC kept as it is when it is AAC)
or an mp3, with tags and a cover written into the file, saved in the extraction folder and scanned
into the library as the "extracted" kind.

The extraction folder (settings.extract_dir, library/cover music) sits beside the music folder,
mounted writable, and lists in the library as its "cover music" folder (library_paths.py); the
library stays read-only, and nothing is written anywhere else. YouTube needs yt-dlp and
a JavaScript runtime (deno, in the image) and is off until an admin turns it on (appconf
extract_youtube: YouTube's terms allow downloads only where it permits them).

The tags: the song the video is linked to when it is. Else the AI (when a key is set and
extract_ai is on) reads the title, channel and description into artist, title, version...; without
it the title is read as "Artist - Title" ([MV], (Official Video)... left out). Then Bugs is searched
for that song: found (same title, the artist fitting), its official names, album, year, genre and
track number are used (for a live or other version only its artist and genre: the album would be
the studio one). The lyrics (Bugs, LRCLIB, AlSong) go into the file. A job is marked "to check"
when the AI wasn't sure, said it isn't music, or Bugs didn't have the song.
The cover is the video's thumbnail cut square (Bugs' album cover, then the linked album's, only when
there is none). Saved as cover music/<artist>/<disc>-<track> <title>.m4a (eztag's
"%disc%-%track% %title%"). Nothing is made up: what isn't known is left empty. Jobs run one at a
time in the background (ExtractJob).
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
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image
from sqlalchemy import select

from . import ai_banner, appconf, lyrics_fetch, search_index, transcode
from .config import settings
from .db import SessionLocal
from .library_paths import extract_top, library_path, library_rel
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
    """The extraction folder's top-level name in the library, or None when it can't be one (set
    deeper inside the music folder)."""
    if (top := extract_top()) is not None:
        return top
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
        "ai": appconf.get("extract_ai") == "on", "ai_ready": ai_banner.configured(),
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
                  "channel": video.channel, "track_id": video.track_id, "album_id": video.album_id, "duration": video.duration}
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
        rel = library_rel(target).replace(os.sep, "/")
        _set(job_id, step="scan", file_path=rel, found={k: v for k, v in tags.items() if k != "lyrics"})
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
    t = re.sub(r"\s+(?:official\s+)?(?:m/?v|music video|lyric video|performance video)\b", "", t, flags=re.I)  # a bare "Official MV"
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
    """The tags to write and the cover (JPEG bytes): the linked song's, else found from the video
    (the AI or its title, then Bugs). Also the lyrics, and what to check ("review")."""
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
                "disc": track.disc_no or 1, "source": "track", "review": [],
            }
        album_cover = cover_file(album.id, "large") if album is not None and album.cover_path else None
    length = info.get("duration") or source.get("duration")
    bugs_cover = None
    if track is None:
        tags, bugs_cover = _find(source, info, album)
    tags["comment"] = url
    # the lyrics (Bugs' own when the song was found there), only for a song that is known: a title
    # alone finds some other song's
    text, where = None, None
    if tags["artist"] and "no_match" not in tags["review"]:
        text, where = lyrics_fetch.by_name(tags["title"], tags["artist"], tags["album"], length, (tags.get("bugs") or {}).get("track"))
    tags["lyrics"], tags["lyrics_from"] = text, where
    # the cover: the video's own picture (its thumbnail cut square); Bugs' or the linked album's only without one
    cover = _thumbnail(source)
    tags["cover"] = ("youtube" if source["youtube_id"] else "video") if cover else None
    if cover is None and bugs_cover:
        cover, tags["cover"] = _fetch_cover(bugs_cover), "bugs"
    if cover is None and album_cover is not None and album_cover.is_file():
        cover, tags["cover"] = album_cover.read_bytes(), "album"
    return tags, cover


_VERSION = re.compile(r"\s*[(\[]([^)\]]*\b(?:live|acoustic|remix|ver\.?|version|cover|inst\.?|instrumental|unplugged|라이브|어쿠스틱|리믹스)\b[^)\]]*)[)\]]\s*", re.I)
REVIEW_CONFIDENCE = 0.6


def _find(source: dict, info: dict, album: Album | None) -> tuple[dict, str | None]:
    """Tags for a video linked to no song: read by the AI (or off its title), confirmed on Bugs.
    Returns them and Bugs' album cover address (None when not found there)."""
    title_in, channel = info.get("title") or source["title"], info.get("channel") or info.get("uploader") or source["channel"]
    review: list[str] = []
    read = _ai(title_in, channel, info.get("description") or "", info.get("duration") or source.get("duration"))
    if read is not None:
        artist, title, version = read["artist"], read["title"], read["version"]
        if not read["is_music"]:
            review.append("not_music")
        elif read["confidence"] < REVIEW_CONFIDENCE:
            review.append("unsure")
    else:
        artist, title = parse_title(title_in, channel)
        m = _VERSION.search(title)
        version = m.group(1).strip() if m else ""
        title = _VERSION.sub(" ", title).strip() if m else title
    found = _bugs(artist, title) if artist and title else None
    tags = {"title": title, "artist": artist, "album": "", "album_artist": artist, "year": "", "genre": "", "track": 1, "disc": 1,
            "source": "ai" if read is not None else "title", "version": version, "review": review}
    if read is not None:
        tags |= {"album": read["album"], "year": read["year"], "genre": read["genre"], "featured": read["featured"]}
    cover = None
    if found is None:
        tags["review"].append("no_match")
        if tags.get("featured"):
            tags["title"] = f"{title} (Feat. {tags['featured']})"
    else:
        tags["review"] = [r for r in review if r != "unsure"]  # Bugs has that artist's song by that title
        tags["bugs"] = {"track": found["track_id"], "album": found["album_id"]}
        tags["artist"] = found["artist"]
        tags["genre"] = found["genre"] or tags["genre"]
        if version:  # the video's own version: Bugs' album and number would be the studio recording's
            tags["title"], tags["album_artist"] = found["title"], found["album_artist"] or found["artist"]
        else:
            tags |= {"title": found["title"], "album": found["album"], "album_artist": found["album_artist"] or found["artist"],
                     "year": found["year"] or tags["year"], "track": found["track"] or 1, "disc": found["disc"] or 1}
            cover = found["cover"]
    if version:
        tags["title"] = f"{tags['title']} ({version})"
    if not tags["album"]:  # a single of its own
        tags["album"] = album.title if album else tags["title"]
    if not tags["year"] and album and album.year:
        tags["year"] = str(album.year)
    return tags, cover


# ---- the AI's reading of a video ----
AI_SCHEMA = {
    "type": "object",
    "properties": {
        "artist": {"type": "string"}, "title": {"type": "string"}, "featured": {"type": "string"}, "album": {"type": "string"},
        "year": {"type": "string"}, "genre": {"type": "string"}, "version": {"type": "string"},
        "is_music": {"type": "boolean"}, "confidence": {"type": "number"},
    },
    "required": ["artist", "title", "featured", "album", "year", "genre", "version", "is_music", "confidence"],
    "additionalProperties": False,
}
AI_GUIDE = """You read a music video's title, channel and description and say which song it is, for the
tags of an audio file. Answer in JSON:
- artist: the main performing artist as usually written (e.g. "아이유", "BTS", "NewJeans"); for a
  cover or a live performance, the one performing in the video
- title: the song title only: no [MV], (Official Video), M/V, 4K, | channel, lyrics, "가사" and the like
- featured: featured artists ("" if none)
- album: the album the song is from, only when the title or description says it ("" otherwise)
- year: release year only when stated ("" otherwise); genre: only when clear ("" otherwise)
- version: "Live", "Acoustic", "Remix", "Cover", "Inst." or similar when the video is such a version
  of the song ("" for the original recording or its music video)
- is_music: false when the video is not a song (a talk, a vlog, a trailer, a compilation of songs)
- confidence: 0..1, how sure you are of artist and title
Never invent: leave a field empty when the video doesn't say it. Keep the names' own language."""


def _ai(title: str, channel: str, description: str, length: float | None) -> dict | None:
    """The AI's reading (None: not set up, turned off, or it failed: the title rules are used)."""
    if appconf.get("extract_ai") != "on" or not ai_banner.configured():
        return None
    from .ai_playlist import ask_json

    prompt = f"Title: {title}\nChannel: {channel}\nLength: {int(length or 0)} s\nDescription:\n{(description or '')[:1500]}"
    try:
        r = ask_json(AI_GUIDE, prompt, AI_SCHEMA, "music_video_tags")
    except Exception as exc:  # noqa: BLE001 - the title rules instead
        log.info("extract AI failed for %s: %s", title, exc)
        return None
    try:
        out = {k: " ".join(str(r.get(k) or "").split())[:200] for k in ("artist", "title", "featured", "album", "year", "genre", "version")}
        out["year"] = m.group() if (m := re.search(r"(?:19|20)\d{2}", out["year"])) else ""
        out["is_music"], out["confidence"] = bool(r.get("is_music", True)), float(r.get("confidence") or 0)
    except (TypeError, ValueError, AttributeError):
        return None
    return out if out["title"] else None


# ---- Bugs: the song's official tags ----
BUGS = "https://music.bugs.co.kr/"


def _bugs_page(url: str) -> BeautifulSoup:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": BUGS, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed host
        return BeautifulSoup(resp.read().decode("utf-8", "replace"), "html.parser")


def _plain(text: str) -> str:
    return search_index.norm(lyrics_fetch._clean_title(text or "")).replace(" ", "")


def _bugs(artist: str, title: str) -> dict | None:
    """The song on Bugs with this title whose artist fits (None: not there, or Bugs didn't answer)."""
    try:
        soup = _bugs_page(BUGS + "search/track?q=" + urllib.parse.quote(f"{artist} {lyrics_fetch._clean_title(title)}"))
        want_t, want_a = _plain(title), search_index.norm(artist).replace(" ", "")
        row = None
        for tr in soup.select("table.trackList tbody tr[trackid]")[:20]:
            t = tr.select_one("p.title a")
            names = [a.get("title") or a.get_text(strip=True) for a in tr.select("p.artist a")]
            a = search_index.norm(" ".join(names)).replace(" ", "")
            if t and _plain(t.get("title") or t.get_text()) == want_t and want_a and a and (want_a in a or a in want_a):
                row = tr
                break
        if row is None:
            return None
        names = [a.get("title") or a.get_text(strip=True) for a in row.select("p.artist a")]
        t = row.select_one("p.title a")
        found = {
            "track_id": row["trackid"], "album_id": row.get("albumid"), "title": (t.get("title") or t.get_text(strip=True)).strip(),
            "artist": ", ".join(dict.fromkeys(n for n in names if n)), "album": "", "album_artist": "", "year": "", "genre": "",
            "track": None, "disc": None, "cover": None,
        }
        if (a := row.select_one("a.album")) is not None:
            found["album"] = (a.get("title") or a.get_text(strip=True)).strip()
        if found["album_id"]:
            found |= _bugs_album(found["album_id"], found["track_id"])
        return found
    except Exception as exc:  # noqa: BLE001 - Bugs down or changed: not confirmed
        log.info("extract Bugs search failed for %s - %s: %s", artist, title, exc)
        return None


def _bugs_album(album_id: str, track_id: str) -> dict:
    """From a Bugs album page: its artist, year, genre, cover, and the song's number and disc."""
    soup = _bugs_page(f"{BUGS}album/{album_id}")
    out: dict = {}
    if (og := soup.select_one('meta[property="og:title"]')) and " / " in og.get("content", ""):
        out["album_artist"] = og["content"].rsplit(" / ", 1)[1].strip()
    for tr in soup.select("table.info tr"):
        th, td = tr.select_one("th"), tr.select_one("td")
        if not th or not td:
            continue
        key, value = th.get_text(strip=True), " ".join(td.get_text(" ", strip=True).split())
        if key == "발매일" and (m := re.search(r"(?:19|20)\d{2}", value)):
            out["year"] = m.group()
        elif key == "장르":
            out["genre"] = value.split(",")[0].strip()
    if (img := soup.select_one('meta[property="og:image"]')) and img.get("content", "").startswith("https://"):
        out["cover"] = img["content"]
    if (row := soup.select_one(f'tr[trackid="{track_id}"]')) is not None:
        if (n := row.select_one("p.trackIndex em")) and n.get_text(strip=True).isdigit():
            out["track"] = int(n.get_text(strip=True))
        if (c := row.select_one("input[name=check]")) and str(c.get("disc_id") or "").isdigit():
            out["disc"] = int(c["disc_id"])
    return out


def _fetch_cover(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": BUGS})
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - Bugs' image host
            return _square(resp.read(8_000_000))
    except Exception:  # noqa: BLE001
        return None


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
        if tags.get("lyrics"):
            f.tags["\xa9lyr"] = [tags["lyrics"]]
        if cover:
            f.tags["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
        f.save()
        return
    from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, USLT, ID3NoHeaderError

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
    if tags.get("lyrics"):
        f.add(USLT(encoding=3, lang="kor", desc="", text=tags["lyrics"]))
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
    path = library_path(rel).resolve()
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
