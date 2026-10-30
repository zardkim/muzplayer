"""Audiobook scanner: one folder of audio files under AUDIOBOOK_DIR is one book.

Same layout rules as Audiobookshelf, so its library imports one to one (see abs_import):
  author/series/title/files, author/title/files, title/files, or a single file at the top.
  CD1/Disc 2 sub-folders belong to the book above them.
Never modifies the files.
"""

import io
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import mutagen
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Book, ScanJob
from .scanner import AUDIO_EXTS, BATCH, DISC_DIR, FOLDER_COVERS, _embedded_cover, _first, _pick, _read_tags, _walk, _year, check_cancel, nfc

log = logging.getLogger(__name__)

BOOK_EXTS = AUDIO_EXTS | {".m4b"}
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
# covers are usually 2:3 portraits: fit into these boxes, never crop
BOOK_COVER_SIZES = {"thumb": (300, 450), "large": (1000, 1500)}
# fields that come from tags/folders and that an import or a manual edit can pin
META_FIELDS = (
    "title", "subtitle", "authors", "narrators", "series", "series_seq", "genres",
    "published_year", "publisher", "description", "isbn", "asin", "language",
)


def book_cover_file(book_id: int, size: str) -> Path:
    return settings.cover_dir / f"book_{book_id}_{BOOK_COVER_SIZES[size][0]}.jpg"


def save_book_cover(book_id: int, data: bytes) -> bool:
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return False
    settings.cover_dir.mkdir(parents=True, exist_ok=True)
    for size, box in BOOK_COVER_SIZES.items():
        copy = image.copy()
        copy.thumbnail(box)
        copy.save(book_cover_file(book_id, size), "JPEG", quality=85)
    return True


def remove_book_covers(book_ids: list[int]) -> None:
    for book_id in book_ids:
        for size in BOOK_COVER_SIZES:
            book_cover_file(book_id, size).unlink(missing_ok=True)


def _natural(name: str) -> list:
    return [int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", name)]


def book_key(rel: str) -> tuple[str, int | None]:
    """(book folder relative to the root, disc number from a CD folder) for one audio file."""
    parts = Path(rel).parts
    if len(parts) == 1:
        return rel, None  # a single file at the top is a book by itself
    folders = list(parts[:-1])
    disc = None
    while len(folders) > 1 and (m := DISC_DIR.match(nfc(folders[-1]))):
        disc = int(m.group(1)) if disc is None else disc
        folders.pop()
    return "/".join(folders), disc


def _folder_image(directory: Path) -> Path | None:
    """cover/folder/... first, else any image in the book folder (as Audiobookshelf does)."""
    try:
        images = [e for e in directory.iterdir() if e.suffix.lower() in IMAGE_EXTS and e.is_file()]
    except OSError:
        return None
    for name in FOLDER_COVERS:
        for entry in images:
            if entry.stem.lower() == name:
                return entry
    return min(images, key=lambda e: _natural(e.name)) if images else None


def _embedded_chapters(path: Path, length: float) -> list[tuple[float, float, str]]:
    """Chapters stored in the file: MP4/M4B chapter list or ID3 CHAP frames."""
    try:
        audio = mutagen.File(path)
    except Exception:
        return []
    if audio is None:
        return []
    out: list[tuple[float, float, str]] = []
    chapters = getattr(audio, "chapters", None)  # MP4
    if chapters:
        items = [(float(c.start), nfc(c.title or "")) for c in chapters]
        for i, (start, title) in enumerate(items):
            end = items[i + 1][0] if i + 1 < len(items) else length
            out.append((start, end, title))
    elif audio.tags is not None and hasattr(audio.tags, "getall"):  # ID3
        frames = sorted(audio.tags.getall("CHAP"), key=lambda f: f.start_time)
        for f in frames:
            title = f.sub_frames.get("TIT2")
            out.append((f.start_time / 1000, f.end_time / 1000, nfc(str(title.text[0])) if title else ""))
    return [(max(0.0, s), min(e, length), t) for s, e, t in out if s < length]


# tags easy mode leaves out: MP4 atoms and ID3 frames -> the names _derive reads
MP4_EXTRA = {"©wrt": "composer", "©cmt": "comment", "desc": "description", "ldes": "description", "©pub": "publisher"}
ID3_EXTRA = {"TCOM": "composer", "TPUB": "publisher", "COMM": "comment", "TIT3": "subtitle"}


def _extra_tags(path: Path) -> dict[str, list[str]]:
    try:
        audio = mutagen.File(path)
    except Exception:
        return {}
    tags = getattr(audio, "tags", None)
    out: dict[str, list[str]] = {}
    if tags is None:
        return out
    if hasattr(tags, "getall"):  # ID3
        for frame_id, name in ID3_EXTRA.items():
            for frame in tags.getall(frame_id):
                text = nfc(str(frame.text[0])) if getattr(frame, "text", None) else ""
                if text:
                    out.setdefault(name, []).append(text)
        for frame in tags.getall("TXXX"):
            if frame.desc.casefold() in ("series", "series-part", "asin", "isbn") and frame.text:
                out.setdefault(frame.desc.casefold(), []).append(nfc(str(frame.text[0])))
    elif hasattr(tags, "items"):
        for key, value in tags.items():
            name = MP4_EXTRA.get(key)
            if name is None and key.startswith("----:") and key.rsplit(":", 1)[-1].casefold() in ("series", "series-part", "asin", "isbn"):
                name = key.rsplit(":", 1)[-1].casefold()
            if name:
                values = [nfc(v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)) for v in value]
                out.setdefault(name, []).extend(v for v in values if v)
    return out


def _derive(key: str, first_raw: dict[str, list[str]], single_file: bool) -> dict:
    """Book metadata from the first file's tags, falling back to folder names."""
    parts = Path(key).parts
    folder_title = nfc(Path(key).stem if single_file else parts[-1])
    title = _first(first_raw, "album") or (_first(first_raw, "title") if single_file else "") or folder_title
    authors = ", ".join(_pick(first_raw, "albumartist") or _pick(first_raw, "artist"))
    if not authors and len(parts) >= 2:
        authors = nfc(parts[0])
    series = (first_raw.get("series") or [""])[0]
    if not series and len(parts) >= 3:
        series = nfc(parts[-2])
    seq = (first_raw.get("series-part") or [""])[0]
    if not seq and series:
        m = re.match(r"\s*(?:vol(?:ume)?\.?\s*|book\s*|#)?(\d+(?:\.\d+)?)", folder_title, re.IGNORECASE)
        seq = m.group(1) if m else ""
    return {
        "title": title[:1000],
        "subtitle": (first_raw.get("subtitle") or [""])[0][:1000],
        "authors": authors[:1000],
        "narrators": ", ".join(first_raw.get("composer") or [])[:1000],
        "series": series[:500],
        "series_seq": seq[:32],
        "genres": [g[:200] for g in _pick(first_raw, "genre")][:20],
        "published_year": _year(_first(first_raw, "date")),
        "publisher": (first_raw.get("publisher") or first_raw.get("organization") or [""])[0][:500],
        "description": (first_raw.get("description") or first_raw.get("comment") or [""])[0],
        "isbn": (first_raw.get("isbn") or [""])[0][:32],
        "asin": (first_raw.get("asin") or [""])[0][:32],
        "language": (first_raw.get("language") or [""])[0][:64],
    }


def _read_book(
    root: Path, key: str, entries: list[tuple[str, int | None]], single: bool
) -> tuple[list[dict], list[dict], dict]:
    """Reads every file of a book: (files in play order, chapters, derived metadata)."""
    read = []
    for rel, disc in entries:
        path = root / rel
        st = path.stat()
        raw, length = _read_tags(path)
        if not length:
            raise ValueError(f"unknown duration: {rel}")
        track = re.match(r"\s*(\d+)", _first(raw, "tracknumber") or "")
        disc_no = disc if disc is not None else int(m.group(1)) if (m := re.match(r"\s*(\d+)", _first(raw, "discnumber") or "")) else 0
        order = (disc_no, int(track.group(1)) if track else 10**6, _natural(Path(rel).name))
        read.append((order, rel, st, raw, float(length)))
    read.sort(key=lambda r: r[0])

    files, chapters = [], []
    offset = 0.0
    embedded = [_embedded_chapters(root / rel, length) for _, rel, _, _, length in read]
    for (_, rel, st, raw, length), own in zip(read, embedded, strict=True):
        files.append({"path": rel, "size": st.st_size, "mtime": st.st_mtime, "duration": length, "offset": round(offset, 3)})
        if any(embedded):
            if own:
                chapters += [{"start": round(offset + s, 3), "end": round(offset + e, 3), "title": t} for s, e, t in own]
            else:
                chapters.append({"start": round(offset, 3), "end": round(offset + length, 3), "title": ""})
        elif len(read) > 1:
            title = _first(raw, "title") or nfc(Path(rel).stem)
            chapters.append({"start": round(offset, 3), "end": round(offset + length, 3), "title": title})
        offset += length
    for i, ch in enumerate(chapters, 1):
        ch["title"] = ch["title"][:500] or str(i)
    first = read[0]  # book metadata comes from the first file in play order
    return files, chapters, _derive(key, {**_extra_tags(root / first[1]), **first[3]}, single)


def chapters_fit(chapters: list[dict], duration: float) -> bool:
    return bool(chapters) and all(0 <= c["start"] <= c["end"] <= duration + 2 for c in chapters)


def _apply(book: Book, files: list[dict], chapters: list[dict], meta: dict) -> None:
    locked = set(book.locked or [])
    for field in META_FIELDS:
        if field not in locked:
            setattr(book, field, meta[field])
    book.files = files
    book.duration = round(sum(f["duration"] for f in files), 3)
    # imported chapters stay unless the files changed so much they no longer fit
    if "chapters" in locked and chapters_fit(book.chapters or [], book.duration):
        return
    book.chapters = chapters
    book.locked = sorted(locked - {"chapters"})


def _refresh_cover(book: Book, root: Path, cover_sig: str, image: Path | None) -> None:
    if "cover" in (book.locked or []) and book_cover_file(book.id, "thumb").exists():
        return
    data = None
    if image is not None:
        try:
            data = image.read_bytes()
        except OSError:
            data = None
    if data is None and book.files:
        data = _embedded_cover(root / book.files[0]["path"])
    had = book.has_cover
    book.has_cover = bool(data) and save_book_cover(book.id, data)
    if not book.has_cover:
        remove_book_covers([book.id])
    if book.has_cover or had:
        book.cover_version = (book.cover_version or 0) + 1  # new cover URL
    book.cover_sig = cover_sig


def scan_books(db: Session, job: ScanJob, errors: list[str]) -> None:
    """Adds, updates and marks missing books. Called from the library scan thread."""
    root = settings.audiobook_dir
    if root is None:
        return
    if not root.is_dir():
        raise RuntimeError(f"audiobook_dir_not_found: {root}")
    unavailable: list[str] = []

    def on_error(path: Path, exc: Exception) -> None:
        job.errors += 1
        unavailable.append(os.path.relpath(path, root))
        if len(errors) < 50:
            errors.append(f"audiobooks: cannot read: {path}: {getattr(exc, 'strerror', None) or exc}")

    groups: dict[str, tuple[str, list[tuple[str, int | None]]]] = {}  # NFC key -> (key as on disk, files)
    for path, _ in _walk(root, on_error, set(), exts=BOOK_EXTS):
        rel = os.path.relpath(path, root)
        try:
            rel.encode("utf-8")
        except UnicodeEncodeError:
            on_error(path, ValueError("invalid file name encoding"))
            continue
        key, disc = book_key(rel)
        groups.setdefault(nfc(key), (key, []))[1].append((rel, disc))

    existing = {b.folder_path: b for b in db.scalars(select(Book))}
    if not groups and any(b.missing_at is None for b in existing.values()):
        raise RuntimeError(f"audiobook_library_empty: no audio files found under {root}")

    pending = 0
    for nkey, (key, entries) in sorted(groups.items()):
        check_cancel()  # stops before marking anything missing
        single = len(Path(key).parts) == 1 and not (root / key).is_dir()
        image = None if single else _folder_image(root / key)
        cover_sig = ""
        if image is not None:
            try:
                st = image.stat()
                cover_sig = f"{image.name}:{st.st_size}:{st.st_mtime}"
            except OSError:
                image = None
        book = existing.get(nkey)
        try:
            stats = {rel: (root / rel).stat() for rel, _ in entries}
            sig = sorted((rel, st.st_size, st.st_mtime) for rel, st in stats.items())
            if book is not None:
                stored = sorted((f["path"], f["size"], f["mtime"]) for f in book.files or [])
                if stored == sig and book.cover_sig == cover_sig:
                    if book.missing_at is not None:
                        book.missing_at = None
                        job.books_updated += 1
                        pending += 1
                    continue
            files, chapters, meta = _read_book(root, key, entries, single)
            with db.begin_nested():
                is_new = book is None
                if is_new:
                    book = Book(folder_path=nkey, title=meta["title"], locked=[])
                    db.add(book)
                    db.flush()
                    existing[nkey] = book
                _apply(book, files, chapters, meta)
                book.missing_at = None
                _refresh_cover(book, root, cover_sig, image)
                db.flush()
            if is_new:
                job.books_added += 1
            else:
                job.books_updated += 1
        except Exception as exc:  # one bad book must not stop the scan
            job.errors += 1
            if len(errors) < 50:
                errors.append(f"audiobooks: {key}: {exc}")
        pending += 1
        if pending >= BATCH:
            db.commit()
            pending = 0

    def reachable(key: str) -> bool:
        return not any(u == "." or key == nfc(u) or key.startswith(nfc(u) + "/") for u in unavailable)

    now = datetime.now(UTC)
    for nkey, book in existing.items():
        if nkey not in groups and book.missing_at is None and reachable(nkey):
            book.missing_at = now
            job.books_missing += 1
    db.commit()


def book_file(book: Book, index: int) -> str | None:
    """Absolute path of one file of a book, or None when it is gone or outside the root."""
    root = settings.audiobook_dir
    if root is None or book.missing_at is not None or not 0 <= index < len(book.files or []):
        return None
    rel = os.path.normpath(book.files[index]["path"])
    if os.path.isabs(rel) or rel.startswith(".."):
        return None
    path = os.path.join(root, rel)
    return path if os.path.isfile(path) else None
