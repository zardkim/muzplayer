"""Audiobooks: browse, stream, per-user listening position. Off when AUDIOBOOK_DIR is unset."""

import os

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import abs_import
from ..books import BOOK_COVER_SIZES, book_cover_file, book_file
from ..cache import image_response
from ..config import settings
from ..db import get_db
from ..models import Book, BookProgress, User
from ..security import admin_user, api_error, current_user, now
from .library import AUDIO_TYPES, like

router = APIRouter()


def books_enabled() -> None:
    if settings.audiobook_dir is None:
        raise api_error(404, "audiobooks_off")


def progress_out(p: BookProgress | None) -> dict | None:
    if p is None:
        return None
    return {"position": p.position, "finished": p.finished, "updated_at": p.updated_at}


def book_out(book: Book, progress: BookProgress | None) -> dict:
    return {
        "id": book.id,
        "title": book.title,
        "subtitle": book.subtitle,
        "authors": book.authors,
        "narrators": book.narrators,
        "series": book.series,
        "series_seq": book.series_seq,
        "published_year": book.published_year,
        "duration": book.duration,
        "has_cover": book.has_cover,
        "cover_v": book.cover_version if book.has_cover else 0,
        "chapter_count": len(book.chapters or []),
        "created_at": book.created_at,
        "progress": progress_out(progress),
    }


def with_progress(user_id: int):
    return select(Book, BookProgress).outerjoin(
        BookProgress, and_(BookProgress.book_id == Book.id, BookProgress.user_id == user_id)
    )


@router.get("/books", dependencies=[Depends(books_enabled)])
def list_books(
    q: str = "",
    author: str = "",
    series: str = "",
    sort: str = Query("title", pattern="^(title|author|recent)$"),
    limit: int = Query(60, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    conds = [Book.missing_at.is_(None)]
    if q.strip():
        pattern = like(q.strip())
        conds.append(
            or_(Book.title.ilike(pattern), Book.authors.ilike(pattern), Book.narrators.ilike(pattern), Book.series.ilike(pattern))
        )
    if author:
        conds.append(Book.authors.ilike(like(author)))
    if series:
        conds.append(Book.series == series)
    order = {
        "title": [func.lower(Book.title)],
        "author": [func.lower(Book.authors), Book.series, Book.series_seq, func.lower(Book.title)],
        "recent": [Book.created_at.desc()],
    }[sort]
    if series:  # a series reads in order
        order = [func.lpad(Book.series_seq, 10, "0"), func.lower(Book.title)]
    total = db.scalar(select(func.count()).select_from(Book).where(*conds))
    rows = db.execute(with_progress(user.id).where(*conds).order_by(*order, Book.id).limit(limit).offset(offset))
    return {"items": [book_out(b, p) for b, p in rows], "total": total}


@router.get("/books/continue", dependencies=[Depends(books_enabled)])
def continue_listening(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """Books started and not finished, most recently listened first."""
    rows = db.execute(
        select(Book, BookProgress)
        .join(BookProgress, and_(BookProgress.book_id == Book.id, BookProgress.user_id == user.id))
        .where(Book.missing_at.is_(None), BookProgress.finished.is_(False), BookProgress.position > 0)
        .order_by(BookProgress.updated_at.desc())
        .limit(20)
    )
    return {"items": [book_out(b, p) for b, p in rows]}


def get_book_row(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None or book.missing_at is not None:
        raise api_error(404, "not_found")
    return book


@router.get("/books/{book_id}", dependencies=[Depends(books_enabled)])
def get_book(book_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    book = get_book_row(db, book_id)
    progress = db.get(BookProgress, (user.id, book.id))
    return {
        **book_out(book, progress),
        "description": book.description,
        "genres": book.genres or [],
        "publisher": book.publisher,
        "language": book.language,
        "isbn": book.isbn,
        "asin": book.asin,
        "chapters": book.chapters or [],
        # paths stay on the server: the player only needs the timeline
        "files": [{"duration": f["duration"], "offset": f["offset"]} for f in book.files or []],
    }


@router.get("/books/{book_id}/cover", dependencies=[Depends(books_enabled)])
def get_book_cover(
    request: Request,
    book_id: int,
    size: str = Query("thumb", pattern="^(thumb|large)$"),
    v: int | None = None,
    _: User = Depends(current_user),
):
    path = book_cover_file(book_id, size)
    if size not in BOOK_COVER_SIZES or not path.exists():
        raise api_error(404, "not_found")
    return image_response(request, path, versioned=v is not None)


@router.get("/books/{book_id}/files/{index}/stream", dependencies=[Depends(books_enabled)])
def stream_book_file(book_id: int, index: int, _: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    book = db.get(Book, book_id)
    path = book_file(book, index) if book else None
    if path is None:
        raise api_error(404, "not_found")
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    # Safari refuses .m4b served as anything but audio/mp4
    media_type = AUDIO_TYPES.get(ext, "application/octet-stream")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


class ProgressIn(BaseModel):
    position: float = Field(ge=0)
    finished: bool = False


@router.put("/books/{book_id}/progress", dependencies=[Depends(books_enabled)])
def save_progress(book_id: int, body: ProgressIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """Last write wins: the newest save from any device is the position."""
    book = get_book_row(db, book_id)
    row = db.get(BookProgress, (user.id, book.id))
    if row is None:
        row = BookProgress(user_id=user.id, book_id=book.id)
        db.add(row)
    row.position = min(body.position, book.duration or body.position)
    row.finished = body.finished
    row.updated_at = now()
    db.commit()
    return progress_out(row)


@router.delete("/books/{book_id}/progress", status_code=204, dependencies=[Depends(books_enabled)])
def reset_progress(book_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    row = db.get(BookProgress, (user.id, book_id))
    if row is not None:
        db.delete(row)
        db.commit()


# ---- admin ----


@router.get("/admin/books/status", dependencies=[Depends(books_enabled)])
def books_status(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    present = db.scalar(select(func.count()).select_from(Book).where(Book.missing_at.is_(None)))
    missing = db.scalar(select(func.count()).select_from(Book).where(Book.missing_at.is_not(None)))
    imported = db.scalar(select(func.count()).select_from(Book).where(Book.abs_id.is_not(None), Book.missing_at.is_(None)))
    return {
        "folder": str(settings.audiobook_dir),
        "books": present,
        "missing": missing,
        "imported": imported,
        "import": {k: v for k, v in abs_import.state.items()},
    }


class AbsIn(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(min_length=1, max_length=2000)


class AbsImportIn(AbsIn):
    user_map: dict[str, int] = Field(default_factory=dict)  # Audiobookshelf user id -> muzplayer user id


@router.post("/admin/books/abs-import/preview", dependencies=[Depends(books_enabled)])
def abs_preview(body: AbsIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    try:
        return abs_import.preview(db, body.url, body.api_key)
    except abs_import.AbsError as exc:
        raise api_error(400, str(exc)) from None


@router.post("/admin/books/abs-import", status_code=202, dependencies=[Depends(books_enabled)])
def abs_run(body: AbsImportIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    known = set(db.scalars(select(User.id)))
    if any(user_id not in known for user_id in body.user_map.values()):
        raise api_error(400, "validation")
    try:
        started = abs_import.start(body.url, body.api_key, body.user_map)
    except abs_import.AbsError as exc:
        raise api_error(400, str(exc)) from None
    if not started:
        raise api_error(409, "scan_running")
    return abs_import.state
