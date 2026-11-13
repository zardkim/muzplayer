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

import base64
import importlib
import io
import logging
import os
import re
import shutil
import subprocess
import sys
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

from . import ai_banner, appconf, artist_aliases, lyrics_fetch, search_index, transcode
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
_lock = threading.Lock()  # held while a job runs or a song's tags are edited (backup.restore waits for none)
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
        "ai": appconf.get("extract_ai") == "on", "ai_ready": ai_banner.configured(), "ytdlp_update": update_state(),
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
    tags, bugs_cover, album_cover = _identify(source, info)
    length = info.get("duration") or source.get("duration")
    tags["lyrics"], tags["lyrics_from"] = _lyrics(tags, length)
    # the cover: the video's own picture (its thumbnail cut square); Bugs' or the linked album's only without one
    cover = _thumbnail(source)
    tags["cover"] = ("youtube" if source["youtube_id"] else "video") if cover else None
    if cover is None and bugs_cover:
        cover, tags["cover"] = _fetch_cover(bugs_cover), "bugs"
    if cover is None and album_cover is not None and album_cover.is_file():
        cover, tags["cover"] = album_cover.read_bytes(), "album"
    return tags, cover


def _lyrics(tags: dict, length: float | None) -> tuple[str | None, str | None]:
    """(lyrics, where from) for a song that is known: Bugs' own when it was found there; a cover's
    are its original's. A title alone would find some other song's."""
    if tags.get("original"):
        o = tags["original"]
        return lyrics_fetch.by_name(o["title"], o["artist"], "", length, o.get("bugs"))
    if tags["artist"] and "no_match" not in tags["review"]:
        return lyrics_fetch.by_name(tags["title"], tags["artist"], tags["album"], length, (tags.get("bugs") or {}).get("track"))
    return None, None


def _identify(source: dict, info: dict) -> tuple[dict, str | None, Path | None]:
    """The tags (no lyrics, no cover yet), Bugs' album cover address and the linked album's cover file."""
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
            # the singer the video's title names, when it isn't the song's: a cover ("소향 - Love wins all"
            # linked to IU's song): that singer, the song's title and genre; not the original's album
            named = parse_title(info.get("title") or source["title"], "")[0]
            singer = db.get(Artist, track.artist_id) if track.artist_id else None
            names = [track.artist_text or "", *([singer.name, singer.display_name or "", *artist_aliases.visible(singer)] if singer else [])]
            if named and not _fits(named, names):
                tags |= {"artist": named, "album_artist": named, "album": track.title, "year": "", "track": 1, "disc": 1,
                         "source": "title", "original": {"artist": track.artist_text or "", "title": track.title}}
        album_cover = cover_file(album.id, "large") if album is not None and album.cover_path else None
    bugs_cover = None
    if track is None:
        tags, bugs_cover = _find(source, info, album)
    tags["comment"] = url
    return tags, bugs_cover, album_cover


_VERSION = re.compile(r"\s*[(\[]([^)\]]*\b(?:live|acoustic|remix|ver\.?|version|cover|inst\.?|instrumental|unplugged|라이브|어쿠스틱|리믹스)\b[^)\]]*)[)\]]\s*", re.I)
REVIEW_CONFIDENCE = 0.6


def _find(source: dict, info: dict, album: Album | None) -> tuple[dict, str | None]:
    """Tags for a video linked to no song: read by the AI (or off its title), confirmed on Bugs.
    Returns them and Bugs' album cover address (None when not found there)."""
    title_in, channel = info.get("title") or source["title"], info.get("channel") or info.get("uploader") or source["channel"]
    review: list[str] = []
    read = _ai(title_in, channel, info.get("description") or "", info.get("duration") or source.get("duration"))
    named = parse_title(title_in, "")[0]  # the singer the title names ("" when it names none)
    if read is not None:
        artist, title, version = read["artist"], read["title"], read["version"]
        if named and not _fits(named, [artist]):
            artist = named  # the singer in the video's own title, whoever the AI thinks the song is by
        if not read["is_music"]:
            review.append("not_music")
        elif read["confidence"] < REVIEW_CONFIDENCE:
            review.append("unsure")
    else:
        artist, title = parse_title(title_in, channel)
        m = _VERSION.search(title)
        version = m.group(1).strip() if m else ""
        title = _VERSION.sub(" ", title).strip() if m else title
    if version.casefold() in ("cover", "커버"):
        version = ""  # a cover is told by its singer (and listed under covers), not by its title
    found = _bugs(artist, title) if artist and title else None
    original = _bugs("", title) if found is None and title else None  # the song itself, when only one singer has it
    if original is not None and (not artist or _fits(artist, [original["artist"]])):  # the same singer after all
        found, original = original, None
    tags = {"title": title, "artist": artist, "album": "", "album_artist": artist, "year": "", "genre": "", "track": 1, "disc": 1,
            "source": "ai" if read is not None else "title", "version": version, "review": review}
    if read is not None:
        tags |= {"album": read["album"], "year": read["year"], "genre": read["genre"], "featured": read["featured"]}
    cover = None
    if found is None and original is not None and artist:
        # a cover of a song Bugs knows (by someone else): its title, genre and lyrics
        tags["review"] = [r for r in review if r != "unsure"]
        tags |= {"title": original["title"], "genre": original["genre"] or tags["genre"],
                 "original": {"artist": original["artist"], "title": original["title"], "bugs": original["track_id"]}}
        title = original["title"]
    elif found is None:
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


def _fits(name: str, names: list[str]) -> bool:
    """Whether a singer's name is one of these (or within one: "아이유" in "아이유(IU)")."""
    x = search_index.norm(name).replace(" ", "")
    return bool(x) and any(y and (x in y or y in x) for y in (search_index.norm(n).replace(" ", "") for n in names))


def _bugs(artist: str, title: str) -> dict | None:
    """The song on Bugs with this title whose artist fits (None: not there, or Bugs didn't answer).
    Without an artist: the song with this title when only one artist has it (the original of a cover)."""
    try:
        soup = _bugs_page(BUGS + "search/track?q=" + urllib.parse.quote(f"{artist} {lyrics_fetch._clean_title(title)}".strip()))
        want_t = _plain(title)
        row = None
        same: dict[str, object] = {}  # artist -> their first row with this title
        for tr in soup.select("table.trackList tbody tr[trackid]")[:20]:
            t = tr.select_one("p.title a")
            names = [a.get("title") or a.get_text(strip=True) for a in tr.select("p.artist a")]
            if not t or _plain(t.get("title") or t.get_text()) != want_t:
                continue
            if artist and _fits(artist, [" ".join(names)]):
                row = tr
                break
            same.setdefault(search_index.norm(" ".join(names)).replace(" ", ""), tr)
        if row is None and not artist and len(same) == 1:
            row = next(iter(same.values()))
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


def _target(tags: dict, fmt: str, current: Path | None = None) -> Path:
    """extract_dir/<artist>/<disc>-<track> <title>.<fmt> (eztag's "%disc%-%track% %title%": the track
    two digits, the disc as it is), a number added when the name is taken (by another file than
    `current`, the song being renamed)."""
    folder = settings.extract_dir / _safe(tags["album_artist"] or tags["artist"], "Unknown")
    stem = f"{int(tags.get('disc') or 1)}-{int(tags.get('track') or 1):02d} {_safe(tags['title'], 'Untitled')}"
    target = folder / f"{stem}.{fmt}"
    n = 2
    while target.exists() and not (current is not None and target == current):
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
                 "\xa9day": tags["year"], "\xa9gen": tags["genre"], "\xa9cmt": tags.get("comment") or ""}
        for k, v in pairs.items():
            if v:
                f.tags[k] = [v]
            elif k != "\xa9cmt":
                f.tags.pop(k, None)  # emptied in the tag editor
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
        f.delall(frame.__name__)
        if v:
            f.add(frame(encoding=3, text=v))
    f.add(TRCK(encoding=3, text=str(int(tags.get("track") or 1))))
    f.add(TPOS(encoding=3, text=str(int(tags.get("disc") or 1))))
    if tags.get("comment"):
        f.add(COMM(encoding=3, lang="kor", desc="", text=tags["comment"]))
    if tags.get("lyrics"):
        f.delall("USLT")
        f.add(USLT(encoding=3, lang="kor", desc="", text=tags["lyrics"]))
    if cover:
        f.delall("APIC")
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


# ---- 5. the tag editor (an admin fixes what was found) ----
EDITABLE = ("title", "artist", "album", "album_artist", "year", "genre", "track", "disc")
BUGS_IMAGES = "image.bugsm.co.kr"
UPLOAD_MAX = 8_000_000  # bytes of an uploaded cover


def read_tags(path: Path) -> dict:
    """The editable tags in an extracted file, and whether it holds lyrics and a cover."""
    out: dict = {k: "" for k in EDITABLE} | {"track": 1, "disc": 1, "lyrics": False, "cover": False}
    if path.suffix.lower() == ".m4a":
        from mutagen.mp4 import MP4

        t = MP4(path).tags or {}
        first = lambda k: str((t.get(k) or [""])[0])  # noqa: E731
        out |= {"title": first("\xa9nam"), "artist": first("\xa9ART"), "album_artist": first("aART"), "album": first("\xa9alb"),
                "year": first("\xa9day"), "genre": first("\xa9gen"), "lyrics": bool(t.get("\xa9lyr")), "cover": bool(t.get("covr"))}
        out["track"] = (t.get("trkn") or [(1, 0)])[0][0] or 1
        out["disc"] = (t.get("disk") or [(1, 0)])[0][0] or 1
        return out
    from mutagen.id3 import ID3, ID3NoHeaderError

    try:
        t = ID3(path)
    except ID3NoHeaderError:
        return out
    text = lambda k: str(t[k].text[0]) if k in t and t[k].text else ""  # noqa: E731
    number = lambda k: int(m.group()) if (m := re.match(r"\d+", text(k))) else 1  # noqa: E731
    out |= {"title": text("TIT2"), "artist": text("TPE1"), "album_artist": text("TPE2"), "album": text("TALB"), "year": text("TDRC"),
            "genre": text("TCON"), "track": number("TRCK"), "disc": number("TPOS"), "lyrics": bool(t.getall("USLT")), "cover": bool(t.getall("APIC"))}
    return out


def _editable(db, track_id: int) -> tuple[Track, Path, ExtractJob | None, Video | None]:
    """The extracted song (its file in the extraction folder), the job that made it and its video."""
    track = db.get(Track, track_id)
    if track is None:
        raise ExtractError("not_found")
    path = library_path(track.file_path)
    if settings.extract_dir.resolve() not in path.resolve().parents or not path.is_file():
        raise ExtractError("extract_not_extracted")
    job = db.scalar(select(ExtractJob).where((ExtractJob.track_id == track.id) | (ExtractJob.file_path == track.file_path))
                    .order_by(ExtractJob.id.desc()).limit(1))
    video = db.get(Video, job.video_id) if job and job.video_id else None
    return track, path, job, video


def _source(video: Video | None) -> dict | None:
    if video is None:
        return None
    return {"id": video.id, "youtube_id": video.youtube_id, "file_path": video.file_path, "title": video.title,
            "channel": video.channel, "track_id": video.track_id, "album_id": video.album_id, "duration": video.duration}


def edit_info(track_id: int) -> dict:
    with SessionLocal() as db:
        track, path, job, video = _editable(db, track_id)
        return {"track_id": track.id, "album_id": track.album_id, "file_path": track.file_path, "format": path.suffix.lstrip(".").lower(),
                "tags": read_tags(path), "job_id": job.id if job else None,
                "video": {"id": video.id, "title": video.title, "youtube_id": video.youtube_id} if video else None}


def suggest(track_id: int) -> dict:
    """What finding the tags again says (the AI or the title, Bugs): shown in the editor, saved
    only when the admin saves. With Bugs' album cover when it was found there."""
    with SessionLocal() as db:
        _, _, _, video = _editable(db, track_id)
        source = _source(video)
    if source is None:
        raise ExtractError("extract_source")
    tags, bugs_cover, _ = _identify(source, {})
    return {"tags": {k: tags.get(k, "") for k in EDITABLE}, "review": tags.get("review", []), "original": tags.get("original"),
            "bugs": tags.get("bugs"), "bugs_cover": bugs_cover}


def _cover_from(choice: str | None, url: str | None, data: str | None, source: dict | None) -> bytes | None:
    """The new cover: the video's thumbnail, Bugs' album cover (its image host only) or an uploaded
    picture, each cut square. None: keep the file's own."""
    if not choice:
        return None
    if choice == "thumbnail":
        cover = _thumbnail(source) if source else None
    elif choice == "bugs":
        host = urllib.parse.urlsplit(url or "").hostname
        cover = _fetch_cover(url) if host == BUGS_IMAGES and (url or "").startswith("https://") else None
    elif choice == "upload":
        raw = (data or "").split(",", 1)[-1]  # a data: URL or bare base64
        try:
            blob = base64.b64decode(raw, validate=True)
        except ValueError:
            blob = b""
        cover = _square(blob) if 0 < len(blob) <= UPLOAD_MAX else None
    else:
        cover = None
    if cover is None:
        raise ExtractError("extract_cover")
    return cover


def retag(track_id: int, values: dict, cover_choice: str | None = None, cover_url: str | None = None,
          cover_data: str | None = None, lyrics: bool = False) -> dict:
    """Writes the editor's tags (and a new cover, the lyrics found again) into the file, renames it
    to match (cover music/<artist>/<disc>-<track> <title>), and scans it in. The song keeps its row
    (and with it its likes, stars and playlist places): its path is moved in the database first."""
    from .scanner import scan_lock

    if not _lock.acquire(timeout=5):
        raise ExtractError("extract_running")
    try:
        with SessionLocal() as db:
            track, path, job, video = _editable(db, track_id)
            rel, source = track.file_path, _source(video)
        fmt = path.suffix.lstrip(".").lower()
        if fmt not in FORMATS:
            raise ExtractError("extract_format")
        tags = read_tags(path) | {k: values[k] for k in EDITABLE if k in values}
        for k in ("title", "artist", "album", "album_artist", "year", "genre"):
            tags[k] = " ".join(str(tags[k] or "").split())[:300]
        tags["track"] = max(1, min(999, int(tags["track"] or 1)))
        tags["disc"] = max(1, min(99, int(tags["disc"] or 1)))
        if not tags["title"]:
            raise ExtractError("extract_no_title")
        tags["album"] = tags["album"] or tags["title"]
        tags["album_artist"] = tags["album_artist"] or tags["artist"]
        cover = _cover_from(cover_choice, cover_url, cover_data, source)
        tags["lyrics"] = None
        if lyrics:
            tags["review"] = []
            tags["lyrics"] = _lyrics(tags, source.get("duration") if source else None)[0]
        _write_tags(path, fmt, tags, cover)
        target = _target(tags, fmt, path)
        new_rel = rel
        if target != path:
            lock = scan_lock()
            if not lock.acquire(timeout=60):
                raise ExtractError("scan_running")
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(path, target)
                new_rel = library_rel(target).replace(os.sep, "/")
                with SessionLocal() as db:
                    db.get(Track, track_id).file_path = new_rel
                    for j in db.scalars(select(ExtractJob).where(ExtractJob.file_path == rel)):
                        j.file_path = new_rel
                    db.commit()
            finally:
                lock.release()
            _prune_empty()
        with SessionLocal() as db:
            for j in db.scalars(select(ExtractJob).where(ExtractJob.file_path == new_rel)):
                j.found = (j.found or {}) | {k: tags[k] for k in EDITABLE} | {"edited": True}
            db.commit()
    finally:
        _lock.release()
    new_id = _scan(new_rel)
    with SessionLocal() as db:
        t = db.get(Track, new_id) if new_id else None
        return {"track_id": new_id, "album_id": t.album_id if t else None, "file_path": new_rel}


# ---- 6. a newer yt-dlp (YouTube changes often; the image's may fall behind) ----
# Installed by an admin into DATA_DIR/pylib (yt-dlp and its JavaScript part alone: the app's other
# libraries stay the image's), found there before the image's own. Loaded afresh after an update.
PYLIB = settings.data_dir / "pylib"
_update = {"state": "idle", "error": None, "at": None}  # idle | running | done | failed


def _use_pylib() -> None:
    if PYLIB.is_dir() and str(PYLIB) not in sys.path:
        sys.path.insert(0, str(PYLIB))


def _forget_ytdlp() -> None:
    """The next import of yt-dlp loads it again (from pylib when there)."""
    for name in list(sys.modules):
        if name.split(".")[0] in ("yt_dlp", "yt_dlp_ejs"):
            del sys.modules[name]
    importlib.invalidate_caches()


_use_pylib()


def update_state() -> dict:
    return dict(_update) | {"custom": PYLIB.is_dir()}


def update_ytdlp() -> dict:
    if _update["state"] == "running":
        raise ExtractError("extract_update_running")
    _update.update(state="running", error=None, at=datetime.now(UTC).isoformat())
    threading.Thread(target=_install, daemon=True, name="ytdlp-update").start()
    return update_state()


def _install() -> None:
    new, old = PYLIB.with_name("pylib.new"), PYLIB.with_name("pylib.old")
    try:
        shutil.rmtree(new, ignore_errors=True)
        run = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-deps", "--no-cache-dir", "--disable-pip-version-check", "--upgrade",
             "--target", str(new), "yt-dlp", "yt-dlp-ejs"],
            capture_output=True, timeout=600, env=os.environ | {"HOME": str(settings.data_dir)},
        )
        if run.returncode or not (new / "yt_dlp").is_dir():
            log.warning("yt-dlp update failed: %s", run.stderr.decode("utf-8", "replace")[-600:])
            raise ExtractError("extract_update_failed")
        with _lock:  # no job is using yt-dlp now
            shutil.rmtree(old, ignore_errors=True)
            if PYLIB.exists():
                PYLIB.rename(old)
            new.rename(PYLIB)
            shutil.rmtree(old, ignore_errors=True)
            _use_pylib()
            _forget_ytdlp()
        log.info("yt-dlp updated to %s", ytdlp_version())
        _update.update(state="done", error=None)
    except ExtractError as exc:
        _update.update(state="failed", error=str(exc))
    except Exception:  # noqa: BLE001
        log.exception("yt-dlp update failed")
        _update.update(state="failed", error="extract_update_failed")
    finally:
        shutil.rmtree(new, ignore_errors=True)


def reset_ytdlp() -> dict:
    """Back to the image's own yt-dlp."""
    if _update["state"] == "running":
        raise ExtractError("extract_update_running")
    with _lock:
        shutil.rmtree(PYLIB, ignore_errors=True)
        if str(PYLIB) in sys.path:
            sys.path.remove(str(PYLIB))
        _forget_ytdlp()
    _update.update(state="idle", error=None)
    return update_state()
