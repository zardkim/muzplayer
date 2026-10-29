from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Album, Artist, Genre, ScanJob, Track, TrackGenre, User
from ..scanner import cover_file, start_scan
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
    missing = db.scalar(select(Track.id).where(Track.missing_at.is_not(None)).limit(1))
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
    """Deletes tracks missing for more than `days`, then unused albums/artists/genres."""
    cutoff = now() - timedelta(days=days)
    deleted = db.execute(delete(Track).where(Track.missing_at.is_not(None), Track.missing_at <= cutoff)).rowcount
    orphan_albums = list(db.scalars(select(Album.id).where(~exists().where(Track.album_id == Album.id))))
    if orphan_albums:
        db.execute(delete(Album).where(Album.id.in_(orphan_albums)))
    db.execute(
        delete(Artist).where(
            ~exists().where(Track.artist_id == Artist.id), ~exists().where(Album.album_artist_id == Artist.id)
        )
    )
    db.execute(delete(Genre).where(~exists().where(TrackGenre.genre_id == Genre.id)))
    db.commit()
    for album_id in orphan_albums:
        for size in ("thumb", "large"):
            cover_file(album_id, size).unlink(missing_ok=True)
    return {"deleted": deleted}


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
