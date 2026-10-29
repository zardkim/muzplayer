import os
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..books import remove_book_covers
from ..models import Book, LibraryFolder, ScanJob, Track, User
from ..scanner import FOLDER_KINDS, nfc, prune_orphans, remove_covers, start_scan
from ..security import admin_user, api_error, delete_user_sessions, hash_password, now
from .auth import user_out

router = APIRouter(prefix="/admin")


def job_out(job: ScanJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "scanned": job.scanned,
        "added": job.added,
        "updated": job.updated,
        "missing": job.missing,
        "errors": job.errors,
        "error_summary": job.error_summary,
        "books_added": job.books_added,
        "books_updated": job.books_updated,
        "books_missing": job.books_missing,
    }


@router.post("/scan", status_code=202)
def scan(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    job = start_scan(db)
    if job is None:
        raise api_error(409, "scan_running")
    return job_out(job)


@router.get("/scan/latest")
def latest_scan(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    job = db.scalars(select(ScanJob).order_by(ScanJob.id.desc()).limit(1)).first()
    missing = db.scalar(select(Track.id).where(Track.missing_at.is_not(None)).limit(1)) or db.scalar(
        select(Book.id).where(Book.missing_at.is_not(None)).limit(1)
    )
    return {
        "job": job_out(job) if job else None,
        "has_missing": missing is not None,
        "auto_scan_minutes": settings.scan_interval_minutes,
    }


@router.get("/scan/{job_id}")
def get_scan(job_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    job = db.get(ScanJob, job_id)
    if job is None:
        raise api_error(404, "not_found")
    return job_out(job)


@router.delete("/missing-tracks")
def purge_missing(
    days: int = Query(30, ge=0, le=3650), _: User = Depends(admin_user), db: Session = Depends(get_db)
):
    """Deletes tracks and audiobooks missing for more than `days`, then unused albums/charts/artists/genres.

    A deleted book takes everyone's listening position with it.
    """
    cutoff = now() - timedelta(days=days)
    deleted = db.execute(delete(Track).where(Track.missing_at.is_not(None), Track.missing_at <= cutoff)).rowcount
    books = list(db.scalars(delete(Book).where(Book.missing_at.is_not(None), Book.missing_at <= cutoff).returning(Book.id)))
    orphan_albums = prune_orphans(db)
    db.commit()
    remove_covers(orphan_albums)
    remove_book_covers(books)
    return {"deleted": deleted, "books_deleted": len(books)}


def suggest_kind(name: str) -> str | None:
    """Guess from the folder name; only shown as a suggestion, never applied by itself."""
    n = name.casefold()
    if "차트" in n or "chart" in n:
        return "chart"
    if any(w in n for w in ("테마", "theme", "모음", "playlist")):
        return "theme"
    if any(w in n for w in ("컴필", "옴니버스", "compilation", "various", "omnibus", "soundtrack")) or re.search(
        r"(?<![a-z])ost(?![a-z])", n
    ):
        return "compilation"
    return None


@router.get("/folders")
def list_folders(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Top-level folders of the library with their kind and how many tracks they hold."""
    kinds = {f.path: f.kind for f in db.scalars(select(LibraryFolder))}
    names: set[str] = set()
    try:
        for entry in os.scandir(settings.music_dir):
            if not entry.name.startswith((".", "@")) and entry.is_dir(follow_symlinks=True):
                names.add(nfc(entry.name))
    except OSError:
        pass  # library not mounted: still show the stored kinds
    counts: dict[str, int] = {}
    top = func.split_part(Track.file_path, "/", 1)
    rows = db.execute(
        select(top, func.count()).where(Track.missing_at.is_(None), Track.file_path.contains("/")).group_by(top)
    )
    for name, count in rows:
        counts[nfc(name)] = counts.get(nfc(name), 0) + count
    books = settings.audiobook_dir
    books_top = None  # the audiobook folder when it sits right inside the music folder (never scanned as music)
    if books is not None and os.path.normpath(books.parent) == os.path.normpath(settings.music_dir):
        books_top = nfc(books.name)
    items = [
        {
            "path": name,
            "kind": kinds.get(name, "album"),
            "suggested": suggest_kind(name),
            "track_count": counts.get(name, 0),
            "present": name in names,
            "audiobooks": name == books_top,
        }
        for name in sorted(names | set(kinds), key=str.casefold)
    ]
    return {"items": items}


class FolderKind(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    kind: str = Field(pattern="^(" + "|".join(FOLDER_KINDS) + ")$")


@router.put("/folders")
def set_folder_kind(body: FolderKind, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Takes effect on the next scan."""
    path = nfc(body.path)
    if not path or "/" in path or "\\" in path or path in (".", ".."):
        raise api_error(400, "invalid_folder")
    row = db.get(LibraryFolder, path)
    if body.kind == "album":
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(LibraryFolder(path=path, kind=body.kind))
    else:
        row.kind = body.kind
    db.commit()
    return {"path": path, "kind": body.kind}


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(default="", max_length=100)
    is_admin: bool = False


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


@router.get("/users")
def list_users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {"items": [user_out(u) for u in db.scalars(select(User).order_by(User.id))]}


@router.post("/users", status_code=201)
def create_user(body: UserCreate, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise api_error(409, "username_taken")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
        is_admin=body.is_admin,
    )
    db.add(user)
    db.commit()
    return user_out(user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int, body: UserPatch, admin: User = Depends(admin_user), db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if user is None:
        raise api_error(404, "not_found")
    if user.id == admin.id and (body.is_active is False or body.is_admin is False):
        raise api_error(400, "cannot_change_self")
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            delete_user_sessions(db, user.id)
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        user.failed_logins = 0
        user.locked_until = None
        delete_user_sessions(db, user.id)
    db.commit()
    return user_out(user)
