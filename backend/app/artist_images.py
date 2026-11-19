"""Artist photos: an artist.jpg in the artist's folder, or a photo from Wikipedia (Wikimedia Commons).

Lookups run only when an admin asks (all artists without a photo, or a pick for one artist) and
stay well under Wikimedia's request limits. Picking a photo for one artist also searches Melon, Bugs
and Apple Music's artist pages (their search pages, parsed like eztag's metadata/ scrapers do).
Photos are downloaded and kept in the cover folder in two sizes, never loaded from those sites by
the browser.
"""

import io
import json
import logging
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageOps
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import net
from .config import settings
from .db import SessionLocal
from .models import Album, Artist, LibraryFolder, Track

log = logging.getLogger(__name__)

SIZES = {"thumb": 300, "large": 800}
# only artist.*: a folder.jpg at that depth is usually an album cover (album/<album>/CD1/..., compilations)
FOLDER_NAMES = ("artist.jpg", "artist.jpeg", "artist.png", "artist.webp")
WIKIS = ("ko", "en")
TIMEOUT = 15
PAUSE = 1.0  # seconds between artists: Wikimedia answers 429 to bursts
THUMB = "500"  # one of Wikimedia's standard thumbnail widths (others are made on demand and rate-limited)
RECHECK = timedelta(days=30)  # an artist Wikipedia had nothing for is looked up again after this
# the article must be about music: its short description says so
MUSIC = re.compile(
    r"가수|밴드|그룹|음악|래퍼|싱어|아이돌|작곡가|프로듀서|연주자|피아니스트|기타리스트|오케스트라|듀오|DJ|"
    r"singer|band|group|music|rapper|songwriter|composer|producer|duo|orchestra|pianist|guitarist|dj\b|idol",
    re.IGNORECASE,
)


class ImageError(Exception):
    """Carries only a code for the frontend."""


def image_file(artist_id: int, size: str) -> Path:
    return settings.cover_dir / f"artist_{artist_id}_{size}.jpg"


def _save(artist: Artist, data: bytes, source: str) -> None:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    settings.cover_dir.mkdir(parents=True, exist_ok=True)
    for size, px in SIZES.items():
        # square, cut from the top third: faces are usually up there
        square = ImageOps.fit(img, (px, px), Image.Resampling.LANCZOS, centering=(0.5, 0.3))
        tmp = image_file(artist.id, size).with_suffix(".tmp")
        square.save(tmp, "JPEG", quality=86, optimize=True)
        os.replace(tmp, image_file(artist.id, size))
    artist.image_path = source
    artist.image_version = (artist.image_version or 0) + 1


def remove(artist: Artist, forget: bool = True) -> None:
    """Deletes the photo. forget: an admin removed it, so lookups leave this artist alone."""
    for size in SIZES:
        image_file(artist.id, size).unlink(missing_ok=True)
    artist.image_path = "none" if forget else None
    artist.image_version = (artist.image_version or 0) + 1


def has_image(artist: Artist) -> bool:
    return bool(artist.image_path) and artist.image_path != "none"


# ---- artist.jpg in the artist folder (album folders: <top>/.../<artist>/<album>/<file>) ----

def folder_images(db: Session, root: Path) -> bool:
    """Picks up artist.jpg in each artist's folder (album-kind folders only: compilations have no
    artist level). A folder photo always wins over one from Wikipedia. Returns whether a photo changed.

    The artist's folder is one of those above the album's, the nearest first: album/아이유/[2017] Palette,
    album/artists/아이유/[2017] Palette and album/아이유/비정규/[2019] 라이브 all find album/아이유/artist.jpg.
    """
    album_tops = [p for p, k in db.execute(select(LibraryFolder.path, LibraryFolder.kind)) if k == "album"]
    # folders that are not marked keep the default kind, album
    marked = {p for (p,) in db.execute(select(LibraryFolder.path))}
    parts = func.string_to_array(Track.file_path, "/")
    rows = db.execute(
        # the folder the album's folder is in
        select(Album.album_artist_id, func.regexp_replace(Track.file_path, "/[^/]*/[^/]*$", ""))
        .join(Album, Album.id == Track.album_id)
        .where(Track.missing_at.is_(None), func.cardinality(parts) >= 4, Album.album_artist_id.is_not(None))
        .distinct()
    ).all()
    dirs: dict[int, list[str]] = {}
    for artist_id, above in rows:
        top = above.split("/", 1)[0]
        top_nfc = unicodedata.normalize("NFC", top)
        if top_nfc in album_tops or top_nfc not in marked:
            found = dirs.setdefault(artist_id, [])
            levels = above.split("/")
            for n in range(len(levels), 1, -1):  # up to the folder right below the top one
                rel = "/".join(levels[:n])
                if rel not in found:
                    found.append(rel)
    changed = False
    for artist in db.scalars(select(Artist).where(Artist.id.in_(list(dirs)))):
        found = None
        for rel in dirs[artist.id]:
            try:
                names = {e.name.casefold(): e.name for e in os.scandir(root / rel) if e.is_file()}
            except OSError:
                continue
            name = next((names[n] for n in FOLDER_NAMES if n in names), None)
            if name:
                path = root / rel / name
                try:
                    found = f"folder:{rel}/{name}@{int(path.stat().st_mtime)}"
                except OSError:
                    continue  # gone since the listing
                break
        if found and found != artist.image_path:
            try:
                _save(artist, path.read_bytes(), found)
                changed = True
            except Exception as exc:  # a broken image file must not stop the scan
                log.warning("artist image %s: %s", found, exc)
        elif not found and (artist.image_path or "").startswith("folder:"):
            remove(artist, forget=False)  # the file is gone: a looked-up photo may take its place
            changed = True
    return changed


# ---- Wikipedia ----

def _get(url: str, headers: dict | None = None) -> bytes:
    """GET with Wikimedia's manners: a descriptive User-Agent, and on 429 wait as told and retry."""
    for attempt in range(4):
        try:
            return net.get(url, headers=headers or {"User-Agent": net.APP_UA}, timeout=TIMEOUT, limit=8_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            wait = exc.headers.get("Retry-After", "")
            time.sleep(min(30, int(wait)) if wait.isdigit() else 5 * (attempt + 1))
    raise AssertionError("unreachable")


def search(name: str, wiki: str, limit: int = 8) -> list[dict]:
    """Wikipedia articles for the name, with their photo and short description, best first."""
    params = {
        "action": "query", "format": "json", "formatversion": "2", "generator": "search",
        "gsrsearch": name, "gsrlimit": str(limit), "prop": "pageimages|description",
        "piprop": "thumbnail", "pithumbsize": THUMB,
    }
    try:
        data = json.loads(_get(f"https://{wiki}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ImageError("image_unreachable") from exc
    pages = sorted(data.get("query", {}).get("pages", []), key=lambda p: p.get("index", 99))
    return [
        {
            "source": wiki,
            "title": p["title"],
            "description": p.get("description") or "",
            "image": p["thumbnail"]["source"],
            "url": f"https://{wiki}.wikipedia.org/wiki/{urllib.parse.quote(p['title'].replace(' ', '_'))}",
        }
        for p in pages
        if p.get("thumbnail", {}).get("source")
    ]


def _key(text: str) -> str:
    return re.sub(r"[\s\-_.·'’]", "", unicodedata.normalize("NFKC", text).casefold())


# "<name> (<qualifier>)": how Wikipedia tells a musician apart from other things of the same name
QUALIFIERS = {
    "ko": ("가수", "음악가", "밴드", "그룹", "래퍼", "작곡가"),
    "en": ("singer", "musician", "band", "group", "rapper", "South Korean singer", "South Korean band", "composer"),
}


def _by_title(name: str, wiki: str) -> dict | None:
    """The name and its qualified forms in one request, following redirects (블랙핑크 -> BLACKPINK);
    the first that is about music and has a photo."""
    wanted = [name] + [f"{name} ({q})" for q in QUALIFIERS[wiki]]
    params = {
        "action": "query", "format": "json", "formatversion": "2", "redirects": "1", "titles": "|".join(wanted),
        "prop": "pageimages|description", "piprop": "thumbnail", "pithumbsize": THUMB,
    }
    data = json.loads(_get(f"https://{wiki}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}")).get("query", {})
    follow = {r["from"]: r["to"] for r in data.get("normalized", []) + data.get("redirects", [])}
    pages = {p["title"]: p for p in data.get("pages", []) if not p.get("missing")}
    for title in wanted:
        for _ in range(3):  # normalized, then redirected
            title = follow.get(title, title)
        page = pages.get(title)
        if page and page.get("thumbnail", {}).get("source") and MUSIC.search(page.get("description", "")):
            return {
                "source": wiki,
                "title": page["title"],
                "description": page.get("description", ""),
                "image": page["thumbnail"]["source"],
                "url": f"https://{wiki}.wikipedia.org/wiki/{urllib.parse.quote(page['title'].replace(' ', '_'))}",
            }
    return None


def best_match(name: str) -> dict | None:
    """The article about this artist, or None when unsure: the name itself or with a qualifier
    ("잔나비 (밴드)"), or a search hit with that title, about music and with a photo."""
    want = _key(name)
    try:
        for wiki in WIKIS:
            page = _by_title(name, wiki)
            time.sleep(PAUSE)
            if page:
                return page
            for page in search(name, wiki):
                base = re.sub(r"\s*\(.*\)\s*$", "", page["title"])
                if _key(base) == want and MUSIC.search(page["description"] + " " + page["title"]):
                    return page
            time.sleep(PAUSE)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ImageError("image_unreachable") from exc
    return None


# ---- Melon, Bugs, Apple Music ----

# where each source's photos may be downloaded from
IMAGE_HOSTS = {
    "ko": ("upload.wikimedia.org", "thumb.wikimedia.org"), "en": ("upload.wikimedia.org", "thumb.wikimedia.org"),
    "melon": ("cdnimg.melon.co.kr",), "bugs": ("image.bugsm.co.kr",), "apple": (".mzstatic.com",),
}


def _page(url: str, referer: str) -> BeautifulSoup:
    return net.get_page(url, referer, timeout=TIMEOUT)


def _text(el) -> str:
    return re.sub(r"\s+([,)])", r"\1", re.sub(r"\s+", " ", el.get_text(" ", strip=True))).strip() if el else ""


def _melon(name: str, limit: int) -> list[dict]:
    soup = _page(f"https://www.melon.com/search/artist/index.htm?q={urllib.parse.quote(name)}", "https://www.melon.com/")
    out = []
    for li in soup.select("div.d_artist_list li"):
        a = li.select_one("dt a.ellipsis")
        img = li.select_one("a.thumb img")
        m = re.search(r"goArtistDetail\('(\d+)'", a.get("href", "") if a else "")
        src = re.sub(r"\.jpg[/?].*$", ".jpg", img.get("src") or "") if img else ""
        if not (m and src.startswith("https://cdnimg.melon.co.kr/") and "artistcrop" in src):
            continue  # no photo (the default picture)
        genres = ", ".join(_text(g) for g in li.select("div.genre-info span"))
        out.append({
            "source": "melon", "title": (a.get("title") or "").removesuffix(" - 페이지 이동") or _text(a), "image": src,
            "description": " · ".join(x for x in (_text(li.select_one("dd.gubun")), genres) if x),
            "url": f"https://www.melon.com/artist/timeline.htm?artistId={m[1]}",
        })
        if len(out) >= limit:
            break
    return out


def _bugs(name: str, limit: int) -> list[dict]:
    soup = _page(f"https://music.bugs.co.kr/search/artist?q={urllib.parse.quote(name)}", "https://music.bugs.co.kr/")
    out = []
    for fig in soup.select("ul.artistList figure.artistInfo"):
        a = fig.select_one("a.artistTitle")
        img = fig.select_one("a.thumbnail img")
        m = re.search(r"/artist/(\d+)", a.get("href", "") if a else "")
        src = (img.get("src") or "").split("?")[0] if img else ""
        if not (m and src.startswith("https://image.bugsm.co.kr/artist/images/")):
            continue
        out.append({
            "source": "bugs", "title": _text(a), "image": re.sub(r"/images/\d+/", "/images/500/", src),
            "description": " · ".join(x for x in (_text(fig.select_one(".artistType")), _text(fig.select_one(".artistGenre"))) if x),
            "url": f"https://music.bugs.co.kr/artist/{m[1]}",
        })
        if len(out) >= limit:
            break
    return out


def _apple(name: str, limit: int) -> list[dict]:
    soup = _page(f"https://music.apple.com/kr/search?term={urllib.parse.quote(name)}", "https://music.apple.com/")
    script = soup.find("script", id="serialized-server-data")
    out: list[dict] = []
    seen: set[str] = set()

    def walk(node) -> None:
        if len(out) >= limit:
            return
        if isinstance(node, dict):
            desc = node.get("contentDescriptor")
            art = (node.get("artwork") or {}).get("dictionary", {}).get("url", "") if isinstance(node.get("artwork"), dict) else ""
            if isinstance(desc, dict) and desc.get("kind") == "artist" and art and node.get("title"):
                ident = str(desc.get("identifiers", {}).get("storeAdamID") or desc.get("url"))
                if ident not in seen:
                    seen.add(ident)
                    out.append({
                        "source": "apple", "title": node["title"], "description": "",
                        "image": re.sub(r"\{w\}x\{h\}(\w*)\.\{f\}", r"600x600\1.jpg", art), "url": desc.get("url", ""),
                    })
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    if script:
        walk(json.loads(script.get_text()))
    return out


def candidates(name: str, limit: int = 6) -> list[dict]:
    """Photos for the name from Melon, Bugs, Apple Music and Wikipedia (Korean, English), all at
    once, in that order. A site that fails is left out; ImageError when every one did."""
    jobs = {"melon": _melon, "bugs": _bugs, "apple": _apple, "ko": lambda n, k: search(n, "ko", k), "en": lambda n, k: search(n, "en", k)}

    def one(source: str) -> list[dict] | None:
        try:
            return jobs[source](name, limit)
        except Exception as exc:  # noqa: BLE001 - a site down or changed: the others may still answer
            log.warning("%s artist search failed: %s", source, exc)
            return None

    with ThreadPoolExecutor(len(jobs)) as pool:
        found = list(pool.map(one, jobs))
    if all(f is None for f in found):
        raise ImageError("image_unreachable")
    return [item for f in found if f for item in f]


def _large(source: str, image: str) -> str:
    """The bigger version of a picked photo."""
    if source == "bugs":
        return re.sub(r"/images/\d+/", "/images/1000/", image)
    if source == "apple":
        return re.sub(r"/\d+x\d+(\w*)\.jpg$", r"/1000x1000\1.jpg", image)
    return image


def use_page(db: Session, artist: Artist, page: dict) -> None:
    """Downloads the picked photo (a Wikipedia article's, or a music site's) for this artist."""
    source = page["source"]
    url = urllib.parse.urlsplit(page["image"])
    if url.scheme != "https" or not any(url.hostname == h or (h.startswith(".") and (url.hostname or "").endswith(h)) for h in IMAGE_HOSTS.get(source, ())):
        raise ImageError("image_bad_source")
    try:
        if source in WIKIS:
            data = _get(page["image"])
        else:
            data = _get(_large(source, page["image"]), {"User-Agent": net.BROWSER_UA})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ImageError("image_unreachable") from exc
    _save(artist, data, f"wiki:{source}:{page['title']}" if source in WIKIS else f"{source}:{page['title']}")
    artist.image_checked_at = datetime.now(UTC)


# ---- the photo of the Bugs artist it is linked to (bugs_artists) ----

BUGS_PHOTO = re.compile(r"^https://image\.bugsm\.co\.kr/artist/images/\d+/\d+/\d+\.jpg$")


def from_bugs(artist: Artist, replace: bool = False) -> bool:
    """Its Bugs artist's photo (the artist page's og:image, bugs_artists.read_page), when it has no
    photo; replace: also one taken from Bugs before (another Bugs artist was linked). Never over a
    photo of its folder, picked by hand, or removed by an admin. A Bugs artist without a photo is
    remembered (info.photo_missing) until its page is read again."""
    if not artist.bugs_id or artist.image_path == "none":
        return False
    if has_image(artist) and not (replace and (artist.image_path or "").startswith("bugs:")):
        return False
    info = artist.info or {}
    url = info.get("image") or f"https://image.bugsm.co.kr/artist/images/1200/{artist.bugs_id // 100}/{artist.bugs_id}.jpg"
    if not BUGS_PHOTO.match(url) or info.get("photo_missing"):
        return False
    try:
        _save(artist, _get(url, {"User-Agent": net.BROWSER_UA, "Referer": "https://music.bugs.co.kr/"}), f"bugs:{artist.display_name or artist.name}")
    except urllib.error.HTTPError:
        artist.info = {**info, "photo_missing": True}
        return False
    except (urllib.error.URLError, TimeoutError, OSError, Image.UnidentifiedImageError) as exc:
        log.info("bugs photo %s: %s", artist.name, exc)
        return False
    artist.image_checked_at = datetime.now(UTC)
    return True


# ---- the admin's "find artist photos" run ----

_lock = threading.Lock()
status: dict = {"state": "idle"}


def start_lookup() -> bool:
    """Looks up a photo for every artist without one (not removed by an admin, not checked lately)."""
    if not _lock.acquire(blocking=False):
        return False
    status.clear()
    status.update(state="running", done=0, found=0, total=0)
    threading.Thread(target=_lookup, daemon=True, name="artist-images").start()
    return True


def _lookup() -> None:
    from .scanner import bump_library  # scanner imports this module

    try:
        with SessionLocal() as db:
            cutoff = datetime.now(UTC) - RECHECK
            ids = list(db.scalars(
                select(Artist.id)
                .where(Artist.image_path.is_(None), or_(Artist.image_checked_at.is_(None), Artist.image_checked_at < cutoff))
                .order_by(Artist.sort_name)
            ))
            status["total"] = len(ids)
            for artist_id in ids:
                artist = db.get(Artist, artist_id)
                if artist is None or artist.image_path is not None:
                    status["done"] += 1
                    continue
                try:
                    page = best_match(artist.name)
                    if page:
                        use_page(db, artist, page)
                        status["found"] += 1
                except ImageError as exc:
                    if str(exc) == "image_unreachable":
                        status.update(state="failed", error="image_unreachable")
                        db.commit()
                        return
                except Exception as exc:  # one odd image must not stop the run
                    log.warning("artist image %s: %s", artist.name, exc)
                artist.image_checked_at = datetime.now(UTC)
                status["done"] += 1
                if status["done"] % 20 == 0:
                    bump_library(db)
                    db.commit()
                time.sleep(PAUSE)
            bump_library(db)
            db.commit()
        status["state"] = "done"
    except Exception:
        log.exception("artist photo lookup failed")
        status.update(state="failed", error="unknown")
    finally:
        _lock.release()
