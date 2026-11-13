import asyncio
import logging
import os
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from .. import ai_banner, album_notes, appconf, artist_aliases, artist_images, backup, bugs_artists, merge, search_index, stats, youtube
from ..config import settings
from ..db import get_db
from ..books import remove_book_covers
from ..models import (
    ActivityLog, Album, Artist, Book, Favorite, LibraryFolder, LibraryState, PlayCount, PlaylistTrack, ScanIssue, ScanJob, Track,
    TrackRating, User,
)
from ..scanner import (
    FOLDER_KINDS, in_folder, bump_library, cancel_scan, nfc, prune_orphans, remove_covers, scan_running,
    start_scan, system_dir,
)
from ..security import admin_user, api_error, delete_user_sessions, hash_password, now
from .auth import user_out

router = APIRouter(prefix="/admin")
log = logging.getLogger(__name__)


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
        "folder": job.folder,
        "mode": job.mode,
    }


class ScanIn(BaseModel):
    folder: str | None = Field(default=None, max_length=500)  # one top-level folder; none = everything
    mode: str = Field(default="scan", pattern="^(scan|rescan|reset)$")


@router.post("/scan", status_code=202)
def scan(body: ScanIn | None = None, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    body = body or ScanIn()
    if body.mode != "scan" and body.folder is None:
        raise api_error(400, "folder_required")  # rescan/reset of everything: not offered
    job = start_scan(db, nfc(body.folder) if body.folder else None, body.mode)
    if job is None:
        raise api_error(409, "scan_running")
    return job_out(job)


@router.post("/scan/cancel", status_code=202)
def stop_scan(_: User = Depends(admin_user)):
    """The scan stops after the current file and keeps what it has read so far."""
    if not cancel_scan():
        raise api_error(409, "no_scan_running")
    return {"cancelling": True}


@router.post("/covers/rebuild", status_code=202)
def rebuild_covers(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Remakes every album and audiobook cover from the files, as part of a scan."""
    if scan_running():
        raise api_error(409, "scan_running")
    db.execute(update(Album).where(Album.cover_path.is_not(None)).values(cover_source=None))
    db.execute(update(Book).values(cover_sig="!rebuild"))  # never matches a real signature
    db.commit()
    job = start_scan(db)
    if job is None:
        raise api_error(409, "scan_running")
    return job_out(job)


@router.get("/folders/impact")
def folder_impact(path: str, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """What a reset of this folder would take with it (shown before asking to confirm)."""
    ids = select(Track.id).where(in_folder(nfc(path))).scalar_subquery()

    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.track_id.in_(ids))) or 0

    return {
        "tracks": db.scalar(select(func.count()).select_from(Track).where(in_folder(nfc(path)))) or 0,
        "ratings": count(TrackRating),
        "favorites": count(Favorite),
        "playlist_entries": count(PlaylistTrack),
        "play_counts": count(PlayCount),
    }


@router.get("/scan/latest")
def latest_scan(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    job = db.scalars(select(ScanJob).order_by(ScanJob.id.desc()).limit(1)).first()
    missing = db.scalar(select(Track.id).where(Track.missing_at.is_not(None)).limit(1)) or db.scalar(
        select(Book.id).where(Book.missing_at.is_not(None)).limit(1)
    )
    return {
        "job": job_out(job) if job else None,
        "has_missing": missing is not None,
        "auto_scan_minutes": settings.scan_interval_minutes,
        "search_index_ready": not search_index.outdated(db),
        "issues": db.scalar(select(func.count()).select_from(ScanIssue)),
    }


@router.get("/scan/issues")
def scan_issues(
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(admin_user),
    db: Session = Depends(get_db, scope="function"),
):
    """What the last scans could not read, kept until the next scan of its place: {items, total}.
    Each with the song it is (track_id, album_id) when the library has one from before."""
    cond = [or_(ScanIssue.path.ilike(f"%{q.strip()}%"), ScanIssue.message.ilike(f"%{q.strip()}%"))] if q.strip() else []
    total = db.scalar(select(func.count()).select_from(ScanIssue).where(*cond))
    rows = db.execute(
        select(ScanIssue, Track.id, Track.album_id)
        .outerjoin(Track, Track.file_path == ScanIssue.path)
        .where(*cond)
        .order_by(ScanIssue.path)
        .offset(offset).limit(limit)
    ).all()
    return {
        "items": [{"path": i.path, "message": i.message, "at": i.at, "track_id": tid, "album_id": aid} for i, tid, aid in rows],
        "total": total,
    }


@router.get("/scan/{job_id}")
def get_scan(job_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    job = db.get(ScanJob, job_id)
    if job is None:
        raise api_error(404, "not_found")
    return job_out(job)


@router.delete("/missing-tracks")
def purge_missing(
    days: int = Query(30, ge=0, le=3650), _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")
):
    """Deletes tracks and audiobooks missing for more than `days`, then unused albums/charts/artists/genres.

    A deleted book takes everyone's listening position with it.
    """
    cutoff = now() - timedelta(days=days)
    deleted = db.execute(delete(Track).where(Track.missing_at.is_not(None), Track.missing_at <= cutoff)).rowcount
    books = list(db.scalars(delete(Book).where(Book.missing_at.is_not(None), Book.missing_at <= cutoff).returning(Book.id)))
    orphan_albums = prune_orphans(db)
    bump_library(db)
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
def list_folders(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Top-level folders of the library with their kind and how many tracks they hold."""
    # (recycle bins, @eaDir and the like are never listed: scanner.system_dir)
    kinds = {f.path: f.kind for f in db.scalars(select(LibraryFolder)) if not system_dir(f.path)}
    names: set[str] = set()
    try:
        for entry in os.scandir(settings.music_dir):
            if not system_dir(entry.name) and entry.is_dir(follow_symlinks=True):
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
    books = settings.books_root
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
def set_folder_kind(body: FolderKind, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
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


ONLINE = timedelta(minutes=5)  # seen this recently (any request; the app asks every few minutes while open)


@router.get("/users")
def list_users(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    since = now() - ONLINE
    return {"items": [
        {**user_out(u), "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
         "online": bool(u.last_seen_at and u.last_seen_at > since)}
        for u in db.scalars(select(User).order_by(User.id))
    ]}


# ---- the log (activity.py): sign-ins and admin changes, newest first ----
LOG_KINDS = {
    "login": ("login", "visit", "logout", "switch", "setup", "signup", "password_changed"),
    "failed": ("login_failed", "login_locked"),
    "admin": ("admin",),
}


@router.get("/logs")
def list_logs(
    kind: str | None = Query(None, pattern="^(login|failed|admin)$"),
    user_id: int | None = None,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    _: User = Depends(admin_user),
    db: Session = Depends(get_db, scope="function"),
):
    cond = []
    if kind:
        cond.append(ActivityLog.action.in_(LOG_KINDS[kind]))
    if user_id is not None:
        cond.append(ActivityLog.user_id == user_id)
    if q.strip():
        pattern = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        cond.append(ActivityLog.username.ilike(pattern) | ActivityLog.detail.ilike(pattern) | ActivityLog.ip.ilike(pattern))
    total = db.scalar(select(func.count()).select_from(ActivityLog).where(*cond))
    rows = db.scalars(select(ActivityLog).where(*cond).order_by(ActivityLog.id.desc()).offset(offset).limit(limit))
    return {"items": [
        {"id": r.id, "at": r.at.isoformat(), "user_id": r.user_id, "username": r.username, "action": r.action, "detail": r.detail, "ip": r.ip}
        for r in rows
    ], "total": total}


@router.post("/users", status_code=201)
def create_user(body: UserCreate, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    # "Admin" next to "admin" would be two accounts people can't tell apart (sign-up checks the same)
    if db.scalar(select(User.id).where(func.lower(User.username) == body.username.lower())) is not None:
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
    user_id: int, body: UserPatch, admin: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")
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
        if body.is_active:
            user.pending = False  # approving a sign-up
        else:
            delete_user_sessions(db, user.id)
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        user.failed_logins = 0
        user.locked_until = None
        delete_user_sessions(db, user.id)
    db.commit()
    return user_out(user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Removes an account and everything that was only its own (playlists, likes, stars, history,
    progress). A sign-up that isn't approved is turned down this way too."""
    user = db.get(User, user_id)
    if user is None:
        raise api_error(404, "not_found")
    if user.id == admin.id:
        raise api_error(400, "cannot_change_self")
    db.delete(user)
    db.commit()


class SignupModeIn(BaseModel):
    mode: str = Field(pattern="^(off|approval|open)$")


@router.get("/signup")
def get_signup(_: User = Depends(admin_user)):
    return {"mode": appconf.signup_mode()}


@router.put("/signup")
def set_signup(body: SignupModeIn, _: User = Depends(admin_user)):
    """Who may make an account on the login page: nobody (off), anyone once an admin approves it,
    or anyone."""
    appconf.update({"signup": body.mode})
    return {"mode": appconf.signup_mode()}


def integrations_out() -> dict:
    """Which keys are set (never the keys themselves) and the AI choices."""
    return {
        "ai_provider": appconf.provider(),
        "gemini_image_model": appconf.get("gemini_image_model"),
        "openai_image_model": appconf.get("openai_image_model"),
        "default_models": appconf.DEFAULT_MODELS,
        "gemini_text_model": appconf.get("gemini_text_model"),
        "openai_text_model": appconf.get("openai_text_model"),
        "default_text_models": appconf.DEFAULT_TEXT_MODELS,
        **{f"{k}_set": bool(appconf.get(k)) for k in appconf.SECRETS},
        "ai_banners": ai_banner.configured(),
        "youtube_search": youtube.configured(),
    }


class IntegrationsIn(BaseModel):
    # None = leave as it is; "" = clear (keys) or back to the default model
    ai_provider: str | None = Field(default=None, pattern="^(gemini|openai)$")
    gemini_api_key: str | None = Field(default=None, max_length=500)
    gemini_image_model: str | None = Field(default=None, max_length=100)
    openai_api_key: str | None = Field(default=None, max_length=500)
    openai_image_model: str | None = Field(default=None, max_length=100)
    gemini_text_model: str | None = Field(default=None, max_length=100)
    openai_text_model: str | None = Field(default=None, max_length=100)
    youtube_api_key: str | None = Field(default=None, max_length=500)


@router.get("/integrations")
def get_integrations(_: User = Depends(admin_user)):
    return integrations_out()


@router.put("/integrations")
def put_integrations(body: IntegrationsIn, _: User = Depends(admin_user)):
    try:
        appconf.update(body.model_dump(exclude_none=True))
    except OSError:
        raise api_error(500, "conf_not_writable") from None
    return integrations_out()


@router.get("/integrations/models")
def integration_models(
    provider: str = Query(pattern="^(gemini|openai)$"),
    kind: str = Query("image", pattern="^(image|text)$"),
    _: User = Depends(admin_user),
):
    """Image (or text: AI playlists) models the saved key can use (asked from the provider with the
    key; never sent to the page)."""
    try:
        models = ai_banner.list_models(provider, kind)
    except ai_banner.AiError as exc:
        raise api_error(400, str(exc)) from None
    defaults = appconf.DEFAULT_TEXT_MODELS if kind == "text" else appconf.DEFAULT_MODELS
    return {"models": models, "default": defaults[provider], "current": appconf.get(f"{provider}_{kind}_model")}


# ---- artist photos ----

@router.post("/artist-images/lookup", status_code=202)
def lookup_artist_images(_: User = Depends(admin_user)):
    """Looks up a Wikipedia photo for every artist that has none (in the background)."""
    if not artist_images.start_lookup():
        raise api_error(409, "lookup_running")
    return artist_images.status


@router.get("/artist-images/status")
def artist_images_status(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    with_photo = db.scalar(
        select(func.count()).select_from(Artist).where(Artist.image_path.is_not(None), Artist.image_path != "none")
    )
    return {**artist_images.status, "artists": db.scalar(select(func.count()).select_from(Artist)), "with_photo": with_photo}


@router.get("/artists/{artist_id}/image-candidates")
def artist_image_candidates(artist_id: int, q: str = "", _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Photos for this artist to pick from: Melon, Bugs, Apple Music, then Wikipedia (Korean, English)."""
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise api_error(404, "not_found")
    name = q.strip() or artist.name
    try:
        items = artist_images.candidates(name)
    except artist_images.ImageError as exc:
        raise api_error(502, str(exc)) from None
    return {"items": items}


class ArtistImageIn(BaseModel):
    source: str = Field(pattern="^(ko|en|melon|bugs|apple)$")
    title: str = Field(min_length=1, max_length=300)
    image: str = Field(max_length=2000)
    description: str = Field(default="", max_length=500)
    url: str = Field(default="", max_length=2000)


@router.put("/artists/{artist_id}/image")
def set_artist_image(artist_id: int, body: ArtistImageIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise api_error(404, "not_found")
    try:
        artist_images.use_page(db, artist, body.model_dump())
    except artist_images.ImageError as exc:
        raise api_error(400, str(exc)) from None
    except Exception:
        raise api_error(400, "image_bad_file") from None
    bump_library(db)
    db.commit()
    return {"image_v": artist.image_version}


@router.delete("/artists/{artist_id}/image", status_code=204)
def delete_artist_image(artist_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Removes the photo; lookups then leave this artist alone (picking one brings it back)."""
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise api_error(404, "not_found")
    artist_images.remove(artist)
    bump_library(db)
    db.commit()


# ---- duplicate artists and genres (merge.py) ----
class MergeIn(BaseModel):
    keep: int
    ids: list[int] = Field(min_length=1, max_length=200)


def _kind(kind: str) -> str:
    if kind not in merge.KINDS:
        raise api_error(404, "not_found")
    return kind


@router.get("/duplicates/{kind}")
def duplicates(kind: str, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Names that look like the same artist or genre (suggestions), and the merges made so far."""
    kind = _kind(kind)
    if kind == "artist":  # with why each group was suggested (merge.artist_duplicates)
        groups = merge.artist_duplicates(db)
    else:
        groups = [{"items": g, "reasons": ["spelling"]} for g in merge.duplicates(db, kind)]
    return {"groups": groups, "merged": merge.aliases(db, kind), "not_same": merge.not_same_list(db, kind)}


class NotSameIn(BaseModel):
    names: list[str] = Field(min_length=2, max_length=50)


@router.post("/merge/{kind}/not-same", status_code=204)
def not_same(kind: str, body: NotSameIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """These are different ones: not suggested together again."""
    merge.mark_not_same(db, _kind(kind), body.names)


@router.delete("/merge/{kind}/not-same", status_code=204)
def forget_not_same(kind: str, a: str = Query(min_length=1, max_length=500), b: str = Query(min_length=1, max_length=500),
                    _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    merge.forget_not_same(db, _kind(kind), a, b)


@router.post("/merge/{kind}")
def merge_names(kind: str, body: MergeIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    kind = _kind(kind)
    try:
        return {"merged": merge.merge(db, kind, body.keep, body.ids)}
    except merge.Busy:
        raise api_error(409, "scan_running")
    except LookupError:
        raise api_error(404, "not_found")


@router.delete("/merge/{kind}", status_code=204)
def unmerge(kind: str, name: str = Query(min_length=1, max_length=500), _: User = Depends(admin_user),
            db: Session = Depends(get_db, scope="function")):
    """Undoes a merge: the songs tagged with that name are read again by a scan started now."""
    kind = _kind(kind)
    try:
        if not merge.unmerge(db, kind, name):
            raise api_error(404, "not_found")
    except merge.Busy:
        raise api_error(409, "scan_running")
    start_scan(db)


# ---- album introductions (album_notes.py) ----
class NotesProviderIn(BaseModel):
    provider: str = Field(pattern="^(bugs|melon|off)$")


@router.get("/notes-provider")
def get_notes_provider(_: User = Depends(admin_user)):
    return {"provider": appconf.get("notes_provider")}


@router.put("/notes-provider")
def set_notes_provider(body: NotesProviderIn, _: User = Depends(admin_user)):
    """Where the albums without an introduction are looked up after a scan first (then the other), or off."""
    appconf.update({"notes_provider": body.provider})
    return {"provider": appconf.get("notes_provider")}


# ---- artists' other names (artist_aliases.py) ----
class AliasesSettingIn(BaseModel):
    enabled: bool | None = None
    names: str | None = Field(None, pattern="^(bugs|tag)$")  # artists shown by their Bugs name, or as tagged
    auto_merge: bool | None = None  # artists linked to the same Bugs artist merged by themselves


def aliases_status(db: Session) -> dict:
    with_songs = select(Track.id).where(Track.artist_id == Artist.id, Track.missing_at.is_(None)).exists()
    total, checked, named = db.execute(
        select(func.count(), func.count(Artist.aliases_checked_at), func.count(Artist.id).filter(func.json_array_length(Artist.aliases) > 0))
        .where(with_songs)
    ).one()
    return {
        "enabled": appconf.get("artist_aliases") != "off", "running": artist_aliases.running(), "artists": total, "checked": checked, "named": named,
        "names": appconf.get("artist_names"), "bugs": bugs_artists.stats(db), "auto_merge": appconf.get("artist_auto_merge") != "off",
    }


@router.get("/artist-aliases")
def get_aliases_setting(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    return aliases_status(db)


@router.put("/artist-aliases")
def set_aliases_setting(body: AliasesSettingIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Whether artists' other names and Bugs links are looked up after a scan; which name is shown."""
    if body.enabled is not None:
        appconf.update({"artist_aliases": "on" if body.enabled else "off"})
    if body.auto_merge is not None:
        appconf.update({"artist_auto_merge": "on" if body.auto_merge else "off"})
    if body.names is not None and body.names != appconf.get("artist_names"):
        appconf.update({"artist_names": body.names})
        search_index.index_albums_artists(db)  # sorted by the name shown
        bump_library(db)  # cached lists carry the names
        db.commit()
    return aliases_status(db)


@router.get("/artist-bugs/unsure")
def bugs_unsure(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Artists Bugs has several of under their name, none confirmed: for the admin to pick."""
    rows = db.execute(select(Artist.id, Artist.name).where(Artist.bugs_source == "unsure").order_by(Artist.sort_name).limit(500)).all()
    return {"items": [{"id": i, "name": n} for i, n in rows]}


@router.post("/artist-aliases/run")
def run_aliases(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Looks up the artists not looked up yet now, without waiting for a scan."""
    artist_aliases.lookup_missing()
    return aliases_status(db)


class NotesIn(BaseModel):
    text: str = Field(max_length=album_notes.MAX_TEXT)
    source: str = Field("manual", max_length=200)  # manual | eztag | bugs:<id> | melon:<id>


def _album(db: Session, album_id: int) -> Album:
    album = db.get(Album, album_id)
    if album is None:
        raise api_error(404, "not_found")
    return album


@router.get("/albums/{album_id}/notes/search")
def search_notes(album_id: int, q: str = Query("", max_length=200), _: User = Depends(admin_user),
                 db: Session = Depends(get_db, scope="function")):
    """Albums on Bugs and Melon to take the introduction from (q: the album's artist and title)."""
    album = _album(db, album_id)
    if not q.strip():
        artist = db.get(Artist, album.album_artist_id) if album.album_artist_id else None
        q = f"{artist.name if artist else ''} {album.title}".strip()
    db.commit()  # the sites take seconds: don't hold a pool connection meanwhile
    return {"q": q, "items": album_notes.search(q)}


@router.get("/albums/{album_id}/notes/fetch")
def fetch_notes(album_id: int, provider: str = Query(pattern="^(bugs|melon)$"), id: str = Query(pattern=r"^\d{1,20}$"),
                _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """The introduction on that Bugs/Melon album page, to look at before saving."""
    _album(db, album_id)
    db.commit()  # as above
    try:
        text = album_notes.fetch(provider, id)
    except Exception:  # noqa: BLE001 - the site didn't answer or changed
        raise api_error(502, "notes_unreachable")
    return {"text": text or "", "source": f"{provider}:{id}"}


@router.post("/albums/{album_id}/notes/report")
def reread_report(album_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Reads the eztag album card in the album's folder again."""
    text = album_notes.check_report(db, _album(db, album_id), force=True)
    if not text:
        raise api_error(404, "no_report")
    return {"text": text, "source": "eztag"}


@router.put("/albums/{album_id}/notes")
def save_notes(album_id: int, body: NotesIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    album = _album(db, album_id)
    text = body.text.strip()
    album.description = text or None
    album.description_source = body.source if text else "manual"  # cleared: not looked up again
    db.commit()
    return {"description": album.description, "description_source": album.description_source if text else None}


@router.post("/search-index", status_code=202)
def rebuild_search_index(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Builds the search index of every song, album and artist again, in the background."""
    if scan_running():
        raise api_error(409, "scan_running")
    db.execute(update(LibraryState).values(search_version=0))
    db.commit()
    search_index.rebuild_in_background()


@router.get("/stats")
def statistics(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """The statistics page: library, people, plays of the last 30 days, disk (stats.py)."""
    return stats.collect(db)


# ---- backup and restore (backup.py): the settings and the database, not the library's files ----
_BACKUP_STATUS = {"backup_busy": 409, "backup_busy_scan": 409, "not_found": 404, "backup_invalid": 400, "backup_newer": 400}
UPLOAD_MAX = 4 << 30  # 4 GB


def _backup_error(exc: backup.BackupError):
    code = str(exc)
    return api_error(_BACKUP_STATUS.get(code, 500), code)


@router.get("/backups")
def list_backups(_: User = Depends(admin_user)):
    return {"items": backup.listing(), "keep": backup.KEEP}


@router.post("/backups", status_code=201)
def make_backup(_: User = Depends(admin_user)):
    """A backup now (seconds for most libraries); kept on the server, the last few."""
    try:
        return backup.create()
    except backup.BackupError as exc:
        raise _backup_error(exc) from None


@router.get("/backups/{name}")
def download_backup(name: str, _: User = Depends(admin_user)):
    try:
        path = backup.path_of(name)
    except backup.BackupError as exc:
        raise _backup_error(exc) from None
    return FileResponse(path, media_type="application/gzip", filename=name)


@router.delete("/backups/{name}", status_code=204)
def delete_backup(name: str, _: User = Depends(admin_user)):
    try:
        backup.path_of(name).unlink()
    except backup.BackupError as exc:
        raise _backup_error(exc) from None


@router.get("/restore")
def restore_status(_: User = Depends(admin_user)):
    """The restore started last: running, done (with what was restored) or failed (with a code)."""
    return backup.status


@router.post("/backups/{name}/restore", status_code=202)
def restore_backup(name: str, admin: User = Depends(admin_user)):
    """Replaces the database and the settings with a kept backup's, in the background (GET /restore
    tells how it went). Everyone signs in again."""
    try:
        backup.start_restore(backup.path_of(name))
    except backup.BackupError as exc:
        raise _backup_error(exc) from None
    log.warning("restoring the database from %s, asked by %s", name, admin.username)
    return backup.status


@router.post("/restore", status_code=202)
async def restore_upload(request: Request, admin: User = Depends(admin_user)):
    """A backup file sent as the request body (application/octet-stream): kept with the others,
    then restored as restore_backup does (one that turns out unusable is not kept)."""
    backup.folder().mkdir(parents=True, exist_ok=True)
    name = f"muzplayer-uploaded-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    tmp = backup.folder() / f".{name}.part"
    size = 0
    try:
        with tmp.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > UPLOAD_MAX:
                    raise api_error(413, "backup_too_large")
                f.write(chunk)
        os.chmod(tmp, 0o600)
        os.replace(tmp, backup.folder() / name)
    finally:
        tmp.unlink(missing_ok=True)
    try:
        await asyncio.to_thread(backup.start_restore, backup.folder() / name, True)
    except backup.BackupError as exc:
        (backup.folder() / name).unlink(missing_ok=True)  # not a backup this app can use: not kept
        raise _backup_error(exc) from None
    log.warning("restoring the database from an uploaded backup, asked by %s", admin.username)
    return backup.status
