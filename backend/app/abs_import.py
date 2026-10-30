"""One-time import from Audiobookshelf: metadata, chapters, covers and each user's position.

Books are matched by folder: Audiobookshelf's relPath is relative to its library folder,
the same as muzplayer's book key when both point at the same folder. The API key is used only
for the duration of the request/job and is never stored, logged or put in a URL.
"""

import json
import logging
import re
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from html import unescape
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from .books import save_book_cover
from .db import SessionLocal
from .models import Book, BookProgress, User
from .scanner import _lock, nfc

log = logging.getLogger(__name__)

TIMEOUT = 20
MAX_COVER = 20 * 1024 * 1024

# progress of the running/last import; one at a time (it holds the scan lock)
state: dict = {"status": "idle"}


class AbsError(Exception):
    """Carries only a code for the frontend; never the URL with credentials or the key."""


class AbsClient:
    def __init__(self, url: str, key: str):
        url = url.strip().rstrip("/")
        if not re.match(r"^https?://[^/\s]+", url) or not key.strip():
            raise AbsError("abs_invalid")
        self.base = url
        self.key = key.strip()

    def _open(self, path: str):
        req = urllib.request.Request(self.base + path, headers={"Authorization": f"Bearer {self.key}"})
        try:
            return urllib.request.urlopen(req, timeout=TIMEOUT)  # noqa: S310 - admin-supplied server URL
        except urllib.error.HTTPError as exc:
            raise AbsError("abs_unauthorized" if exc.code in (401, 403) else "abs_bad_response") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AbsError("abs_unreachable") from None

    def get(self, path: str):
        with self._open(path) as res:
            try:
                return json.loads(res.read())
            except ValueError:
                raise AbsError("abs_bad_response") from None

    def raw(self, path: str) -> bytes:
        with self._open(path) as res:
            return res.read(MAX_COVER + 1)[:MAX_COVER]


def _items(client: AbsClient) -> list[dict]:
    """Every audiobook item of every book library (minified)."""
    out = []
    for lib in client.get("/api/libraries").get("libraries", []):
        if lib.get("mediaType") != "book":
            continue
        page = 0
        while True:
            data = client.get(f"/api/libraries/{lib['id']}/items?minified=1&limit=200&page={page}")
            results = data.get("results", [])
            out += [
                r for r in results
                # older versions may not send numAudioFiles: keep the item then
                if not r.get("isMissing") and not r.get("isInvalid") and (r.get("media") or {}).get("numAudioFiles", 1)
            ]
            page += 1
            if len(results) < 200 or page * 200 >= data.get("total", 0):
                break
    return out


def _matcher(books: list[Book]):
    by_key = {b.folder_path: b for b in books}

    def match(rel_path: str) -> Book | None:
        rel = nfc(rel_path).strip("/")
        if rel in by_key:
            return by_key[rel]
        # library folders at different depths: the deeper path must end with the shorter one
        hits = [b for k, b in by_key.items() if k.endswith("/" + rel) or rel.endswith("/" + k)]
        return hits[0] if len(hits) == 1 else None

    return match


def _present_books(db: Session) -> list[Book]:
    return list(db.scalars(select(Book).where(Book.missing_at.is_(None))))


def preview(db: Session, url: str, key: str) -> dict:
    client = AbsClient(url, key)
    status = client.get("/status")
    items = _items(client)
    users = client.get("/api/users").get("users", [])
    match = _matcher(_present_books(db))
    matched, unmatched = 0, []
    for item in items:
        if match(item.get("relPath", "")):
            matched += 1
        else:
            unmatched.append(item.get("relPath", ""))
    local = {u.username.casefold(): u.id for u in db.scalars(select(User))}
    return {
        "server_version": status.get("serverVersion", ""),
        "items": len(items),
        "matched": matched,
        "unmatched": sorted(unmatched, key=str.casefold)[:200],
        "unmatched_count": len(unmatched),
        "users": [
            {"id": u["id"], "username": u.get("username", ""), "suggested_user_id": local.get(u.get("username", "").casefold())}
            for u in users
        ],
    }


def _plain(text: str | None) -> str:
    text = re.sub(r"<br\s*/?>|</p>", "\n", text or "", flags=re.IGNORECASE)
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _converter(book: Book, media: dict):
    """Maps a time on Audiobookshelf's timeline to ours by file name, so a different file
    order (or a file added since) still lands on the same spot in the same file."""
    prefix = book.folder_path + "/"
    ours: dict[str, dict] = {}
    for f in book.files or []:
        path = nfc(f["path"])
        ours[path[len(prefix):] if path.startswith(prefix) else PurePosixPath(path).name] = f
    by_name = {PurePosixPath(k).name: v for k, v in ours.items()}
    segments, start = [], 0.0
    for af in sorted((a for a in media.get("audioFiles") or [] if not a.get("exclude")), key=lambda a: a.get("index", 0)):
        rel = nfc((af.get("metadata") or {}).get("relPath", ""))
        segments.append((start, float(af.get("duration") or 0), ours.get(rel) or by_name.get(PurePosixPath(rel).name)))
        start += float(af.get("duration") or 0)

    def convert(t: float) -> float | None:
        for i, (seg_start, length, f) in enumerate(segments):
            if t < seg_start + length or i == len(segments) - 1:
                if f is None:
                    return None
                return round(f["offset"] + min(max(0.0, t - seg_start), f["duration"]), 3)
        return None

    return convert


def _apply_item(db: Session, client: AbsClient, book: Book, item_id: str, progress: dict[int, dict]) -> bool:
    """Imports one item into book. Returns whether a cover was saved."""
    media = client.get(f"/api/items/{item_id}?expanded=1").get("media") or {}
    meta = media.get("metadata") or {}
    series = (meta.get("series") or [{}])[0] if meta.get("series") else {}
    year = re.match(r"\s*(\d{4})", str(meta.get("publishedYear") or meta.get("publishedDate") or ""))
    values = {
        "title": nfc(meta.get("title") or "")[:1000] or book.title,
        "subtitle": nfc(meta.get("subtitle") or "")[:1000],
        "authors": ", ".join(nfc(a.get("name", "")) for a in meta.get("authors") or [])[:1000],
        "narrators": ", ".join(nfc(n) for n in meta.get("narrators") or [])[:1000],
        "series": nfc(series.get("name") or "")[:500],
        "series_seq": str(series.get("sequence") or "")[:32],
        "genres": [nfc(g)[:200] for g in meta.get("genres") or []][:20],
        "published_year": int(year.group(1)) if year else None,
        "publisher": nfc(meta.get("publisher") or "")[:500],
        "description": nfc(_plain(meta.get("description"))),
        "isbn": (meta.get("isbn") or "")[:32],
        "asin": (meta.get("asin") or "")[:32],
        "language": (meta.get("language") or "")[:64],
    }
    # only what Audiobookshelf actually has: an empty field there must not wipe what the
    # tags or folder names gave us (it often leaves e.g. the series number blank)
    locked = set(book.locked or [])
    for field, value in values.items():
        if value not in ("", None, []):
            setattr(book, field, value)
            locked.add(field)

    convert = _converter(book, media)
    chapters = []
    for ch in media.get("chapters") or []:
        start, end = convert(float(ch.get("start", 0))), convert(max(0.0, float(ch.get("end", 0)) - 0.001))
        if start is None or end is None:
            chapters = []
            break
        chapters.append({"start": start, "end": round(end + 0.001, 3), "title": nfc(ch.get("title") or "")[:500]})
    if chapters:
        for i, ch in enumerate(chapters, 1):
            ch["title"] = ch["title"] or str(i)
        book.chapters = chapters
        locked.add("chapters")

    cover = False
    if media.get("coverPath"):
        try:
            data = client.raw(f"/api/items/{item_id}/cover?raw=1")
            cover = save_book_cover(book.id, data)
        except AbsError:
            cover = False
        if cover:
            book.has_cover = True
            book.cover_version = (book.cover_version or 0) + 1
            locked.add("cover")
    book.locked = sorted(locked)
    book.abs_id = item_id[:64]

    for user_id, entries in progress.items():
        entry = entries.get(item_id)
        if not entry or (not entry.get("currentTime") and not entry.get("isFinished")):
            continue
        updated = datetime.fromtimestamp((entry.get("lastUpdate") or 0) / 1000, UTC)
        position = convert(float(entry.get("currentTime") or 0)) or 0.0
        row = db.get(BookProgress, (user_id, book.id))
        if row is not None and row.updated_at and row.updated_at >= updated:
            continue  # listened in muzplayer since: keep that
        if row is None:
            row = BookProgress(user_id=user_id, book_id=book.id)
            db.add(row)
        row.position = position
        row.finished = bool(entry.get("isFinished"))
        row.updated_at = updated
        state["progress"] += 1
    return cover


def _run(client: AbsClient, user_map: dict[str, int]) -> None:
    db = SessionLocal()
    try:
        items = _items(client)
        match = _matcher(_present_books(db))
        pairs = [(item["id"], book) for item in items if (book := match(item.get("relPath", "")))]
        state.update(total=len(pairs))
        progress: dict[int, dict] = {}
        for abs_user, user_id in user_map.items():
            data = client.get(f"/api/users/{abs_user}")
            entries = progress.setdefault(user_id, {})
            for p in data.get("mediaProgress") or []:
                if p.get("mediaItemType", "book") == "book" and p.get("libraryItemId"):
                    old = entries.get(p["libraryItemId"])
                    if old is None or (p.get("lastUpdate") or 0) > (old.get("lastUpdate") or 0):
                        entries[p["libraryItemId"]] = p  # two ABS users mapped to one: newest wins
        for item_id, book in pairs:
            try:
                with db.begin_nested():
                    if _apply_item(db, client, book, item_id, progress):
                        state["covers"] += 1
                    db.flush()
                state["books"] += 1
            except AbsError as exc:
                state["failed"].append(f"{book.folder_path}: {exc}")
            except Exception as exc:  # odd data in one item must not stop the rest
                log.exception("audiobookshelf import: %s", book.folder_path)
                state["failed"].append(f"{book.folder_path}: {type(exc).__name__}")
            state["done"] += 1
            if state["done"] % 20 == 0:
                db.commit()
        db.commit()
        state["status"] = "done"
    except AbsError as exc:
        db.rollback()
        state.update(status="failed", error=str(exc))
    except Exception:
        log.exception("audiobookshelf import failed")
        db.rollback()
        state.update(status="failed", error="unknown")
    finally:
        state["finished_at"] = datetime.now(UTC).isoformat()
        db.close()
        _lock.release()


def start(url: str, key: str, user_map: dict[str, int]) -> bool:
    """Starts the import in the background. False when a scan or import is running."""
    client = AbsClient(url, key)
    if not _lock.acquire(blocking=False):
        return False
    state.clear()
    state.update(
        status="running", total=0, done=0, books=0, covers=0, progress=0, failed=[], error=None,
        started_at=datetime.now(UTC).isoformat(), finished_at=None,
    )
    threading.Thread(target=_run, args=(client, user_map), daemon=True, name="abs-import").start()
    return True
