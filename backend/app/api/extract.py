"""Audio taken out of music videos (extract.py), for admins: the jobs, their settings."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import appconf, extract
from ..db import get_db
from ..models import Album, ExtractJob, Track, User, Video
from ..scanner import bump_library, prune_orphans, remove_covers, scan_lock
from ..security import admin_user, api_error

router = APIRouter()
_STATUS = {"extract_folder": 409, "extract_youtube_off": 403, "extract_no_ytdlp": 409, "extract_source": 400, "extract_format": 400}


def _error(exc: extract.ExtractError):
    return api_error(_STATUS.get(str(exc), 400), str(exc))


def job_out(job: ExtractJob, track: Track | None = None, album: Album | None = None) -> dict:
    return {
        "id": job.id, "video_id": job.video_id, "title": job.title, "format": job.format, "status": job.status,
        "step": job.step, "progress": job.progress, "error": job.error, "found": job.found, "file_path": job.file_path,
        "track_id": job.track_id, "album_id": track.album_id if track else None,
        "has_cover": bool(album and album.cover_path), "cover_v": album.cover_version if album else 0,
        "created_at": job.created_at, "finished_at": job.finished_at,
    }


@router.get("/extract/status")
def get_status(_: User = Depends(admin_user)):
    return extract.status()


class SettingsIn(BaseModel):
    youtube: bool | None = None
    format: Literal["m4a", "mp3"] | None = None
    ai: bool | None = None


@router.put("/extract/settings")
def put_settings(body: SettingsIn, _: User = Depends(admin_user)):
    if body.youtube is not None:
        appconf.update({"extract_youtube": "on" if body.youtube else "off"})
    if body.format is not None:
        appconf.update({"extract_format": body.format})
    if body.ai is not None:
        appconf.update({"extract_ai": "on" if body.ai else "off"})
    return extract.status()


class ExtractIn(BaseModel):
    format: Literal["m4a", "mp3"] | None = None


@router.post("/videos/{video_id}/extract", status_code=202)
def extract_video(video_id: int, body: ExtractIn, admin: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Queues the video's sound to be taken out (m4a unless asked otherwise or set so)."""
    video = db.get(Video, video_id)
    if video is None:
        raise api_error(404, "not_found")
    try:
        job = extract.enqueue(db, video, admin.id, body.format or appconf.get("extract_format") or "m4a")
    except extract.ExtractError as exc:
        raise _error(exc) from None
    return job_out(job)


@router.get("/extract/jobs")
def list_jobs(limit: int = Query(100, ge=1, le=500), _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """The latest jobs, newest first, with the song and album each made."""
    rows = db.execute(
        select(ExtractJob, Track, Album)
        .outerjoin(Track, Track.id == ExtractJob.track_id).outerjoin(Album, Album.id == Track.album_id)
        .order_by(ExtractJob.id.desc()).limit(limit)
    ).all()
    return {"items": [job_out(j, t, a) for j, t, a in rows], "running": any(j.status in ("pending", "running") for j, _, _ in rows)}


@router.post("/extract/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    job = db.get(ExtractJob, job_id)
    if job is None:
        raise api_error(404, "not_found")
    if job.status != "failed":
        raise api_error(409, "extract_not_failed")
    job.status, job.error, job.progress, job.step, job.finished_at = "pending", None, 0, "", None
    db.commit()
    extract.start_worker()
    extract._wake.set()
    return job_out(job)


@router.delete("/extract/jobs/{job_id}", status_code=204)
def delete_job(job_id: int, file: bool = False, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Forgets a job; with file=true also deletes the song it made (and scans the folder)."""
    job = db.get(ExtractJob, job_id)
    if job is None:
        raise api_error(404, "not_found")
    if job.status == "running":
        raise api_error(409, "extract_running")
    rel = job.file_path
    db.delete(job)
    db.commit()
    if file and rel:
        try:
            extract.remove_file(rel)
        except extract.ExtractError as exc:
            raise _error(exc) from None
        # the song goes with it now (a scan of a folder left empty is refused: scanner's library_empty)
        lock = scan_lock()
        if not lock.acquire(timeout=30):
            raise api_error(409, "scan_running")
        try:
            db.execute(delete(Track).where(Track.file_path == rel))
            orphans = prune_orphans(db)
            bump_library(db)
            db.commit()
        finally:
            lock.release()
        remove_covers(orphans)
