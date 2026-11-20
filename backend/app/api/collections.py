"""Charts and themes: lists, the collections page and banners (folder banner.jpg or AI-made)."""

import random
import re
import shutil
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, literal_column, or_, select, text
from sqlalchemy.orm import Session

from .. import ai_banner, search_index
from ..cache import shared_json
from ..config import settings
from ..db import get_db
from ..models import Album, Banner, Chart, Genre, Playlist, PlaylistTrack, Track, TrackGenre, User
from ..scanner import DISC_DIR, bump_library, cover_file, nfc
from ..security import admin_user, api_error, current_user
from .library import like, listed_tracks, present_tracks, track_out, track_query

router = APIRouter()

# category (or chart source) folders shown as one: Hillsong is worship music, filed with CCM
SOURCE_GROUPS = [("CCM", re.compile(r"ccm|hillsong|힐송", re.I))]


def source_group(source: str) -> str:
    return next((name for name, rx in SOURCE_GROUPS if rx.search(source)), source)


COVERS_PER_ITEM = 5  # the auto banner is drawn from these


def chart_count():
    return select(func.count(Track.id)).where(Track.chart_id == Chart.id, present_tracks()).scalar_subquery()


def folder_key(chart: Chart) -> str:
    return f"folder:{chart.folder_path}"


def source_key(source: str) -> str:
    return f"source:{source}"


def load_banners(db: Session) -> dict[str, Banner]:
    return {b.key: b for b in db.scalars(select(Banner))}


def banner_out(chart: Chart, banners: dict[str, Banner]) -> dict | None:
    """The banner shown for a collection: its own AI banner, then (charts) the AI banner of its
    source, then banner.jpg in its folder. None means the page draws one from the covers."""
    own = banners.get(folder_key(chart))
    shared = banners.get(source_key(chart.source)) if chart.kind == "chart" and chart.source else None
    for banner, scope in ((own, "collection"), (shared, "source")):
        if banner is not None:
            version = int(banner.updated_at.timestamp())
            return {"url": f"/api/v1/banners/{banner.id}?v={version}", "kind": "ai", "scope": scope, "id": banner.id}
    if chart.banner_file:
        return {"url": f"/api/v1/charts/{chart.id}/folder-banner", "kind": "folder", "scope": "collection", "id": None}
    return None


def cover_albums(db: Session, chart_ids: list[int]) -> dict[int, list[dict]]:
    """Up to five albums with covers per collection, best ranked first: [{id, v}] (v = cover_v)."""
    if not chart_ids:
        return {}
    rows = db.execute(
        select(
            Track.chart_id,
            Track.album_id,
            Album.cover_version,
            func.min(func.coalesce(Track.chart_position, 9999)).label("pos"),
        )
        .join(Album, Album.id == Track.album_id)
        .where(Track.chart_id.in_(chart_ids), present_tracks(), Album.cover_path.is_not(None))
        .group_by(Track.chart_id, Track.album_id, Album.cover_version)
        .order_by(Track.chart_id, "pos", Track.album_id)
    )
    out: dict[int, list[dict]] = {}
    for chart_id, album_id, version, _ in rows:
        albums = out.setdefault(chart_id, [])
        if len(albums) < COVERS_PER_ITEM:
            albums.append({"id": album_id, "v": version})
    return out


def item_out(chart: Chart, count: int, covers: dict[int, list[dict]], banners: dict[str, Banner]) -> dict:
    albums = covers.get(chart.id, [])
    return {
        "id": chart.id,
        "kind": chart.kind,
        "title": chart.title,
        "source": chart.source,
        "track_count": count,
        "cover_albums": albums,
        "banner": banner_out(chart, banners),
        "created_at": chart.created_at,
    }


def ordering(kind: str):
    # chart week folders are named by date: newest first; themes read best alphabetically
    if kind == "theme":
        return [func.lower(Chart.title), Chart.id]
    return [Chart.title.desc(), Chart.source, Chart.id]


@router.get("/charts")
def list_charts(
    request: Request,
    kind: str = Query("chart", pattern="^(chart|theme)$"),
    source: str = "",
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """Chart weeks or themes. source is the chart source, or the theme category."""

    def build():
        count = chart_count()
        conds = [count > 0, Chart.kind == kind]
        all_sources = db.scalars(
            select(Chart.source).where(chart_count() > 0, Chart.kind == kind, Chart.source != "").distinct()
        ).all()
        if source:  # a group: every folder in it
            conds.append(Chart.source.in_([s for s in all_sources if source_group(s) == source] or [source]))
        base = select(Chart, count.label("track_count")).where(*conds)
        total = db.scalar(select(func.count()).select_from(base.subquery()))
        rows = db.execute(base.order_by(*ordering(kind)).limit(limit).offset(offset)).all()
        covers = cover_albums(db, [c.id for c, _ in rows])
        banners = load_banners(db)
        sources = sorted({source_group(s) for s in all_sources})
        return {"items": [item_out(c, n, covers, banners) for c, n in rows], "total": total, "sources": sources}

    return shared_json(request, db, f"charts:{kind}:{source}:{limit}:{offset}", build)


@router.get("/collections/home")
def collections_home(request: Request, _: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """Everything the collections page shows, in one call. The picks change daily, so the day is
    part of the cache key."""
    return shared_json(request, db, f"collections-home:{date.today().isoformat()}", lambda: _collections_home(db))


def _collections_home(db: Session) -> dict:
    rows = db.execute(select(Chart, chart_count().label("n")).where(chart_count() > 0)).all()
    charts = sorted(((c, n) for c, n in rows if c.kind == "chart"), key=lambda r: (r[0].title, r[0].id), reverse=True)
    themes = sorted(((c, n) for c, n in rows if c.kind == "theme"), key=lambda r: (r[0].title.casefold(), r[0].id))

    by_source: dict[str, list] = {}
    for row in charts:
        by_source.setdefault(source_group(row[0].source), []).append(row)
    by_category: dict[str, list] = {}
    for row in themes:
        by_category.setdefault(source_group(row[0].source), []).append(row)
    # the same order all day for everyone, a new one tomorrow
    picks = list(themes)
    random.Random(date.today().isoformat()).shuffle(picks)
    recent = sorted(rows, key=lambda r: (r[0].created_at, r[0].id), reverse=True)[:12]
    # the banners: what came in lately, each source's latest week and three of today's themes,
    # the newest first
    hero = list({r[0].id: r for r in recent[:3] + [weeks[0] for _, weeks in sorted(by_source.items())] + picks[:3]}.values())
    hero.sort(key=lambda r: (r[0].created_at, r[0].id), reverse=True)

    shown = {c.id for c, _ in hero + picks[:12] + recent}
    for weeks in by_source.values():
        shown |= {c.id for c, _ in weeks[:12]}
    for items in by_category.values():
        shown |= {c.id for c, _ in items[:12]}
    covers = cover_albums(db, list(shown))
    banners = load_banners(db)

    def out(items):
        return [item_out(c, n, covers, banners) for c, n in items]

    return {
        "hero": out(hero),
        "sources": [{"source": s, "total": len(w), "items": out(w[:12])} for s, w in sorted(by_source.items())],
        "picks": out(picks[:12]),
        "categories": [
            {"category": cat, "total": len(items), "items": out(items[:12])}
            for cat, items in sorted(by_category.items(), key=lambda kv: (kv[0] == "", kv[0].casefold()))
        ],
        "recent": out(recent),
        "counts": {"charts": len(charts), "themes": len(themes)},
    }


def get_chart_row(db: Session, chart_id: int) -> Chart:
    chart = db.get(Chart, chart_id)
    if chart is None:
        raise api_error(404, "not_found")
    return chart


def folder_disc(path: str) -> int | None:
    """The disc of a song in a CD1 / CD2 folder of a chart or theme (by the folder, not its tags: those
    name the disc of the album it came from)."""
    parts = path.split("/")
    m = DISC_DIR.match(nfc(parts[-2])) if len(parts) > 2 else None
    return int(m.group(1)) if m else None


def chart_order(track: Track) -> tuple:
    """CD1's songs, then CD2's, each by its place in the chart (the numbers may start again on each disc)."""
    pos = track.chart_position
    return (folder_disc(track.file_path) or 0, pos is None, pos or 0, track.file_path)


@router.get("/charts/{chart_id}")
def get_chart(chart_id: int, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    chart = get_chart_row(db, chart_id)
    rows = sorted(
        db.execute(track_query(user.id).where(Track.chart_id == chart_id, present_tracks())),
        key=lambda r: chart_order(r[0]),
    )
    tracks = [
        {**track_out(r), "chart_position": r[0].chart_position, "chart_disc": folder_disc(r[0].file_path)} for r in rows
    ]
    if not tracks:
        raise api_error(404, "not_found")
    covers = cover_albums(db, [chart.id])
    # the shared playlist made from it (the newest), so its page can open that instead of making another
    shared = db.scalar(
        select(Playlist.id).where(Playlist.chart_id == chart.id, Playlist.is_shared.is_(True)).order_by(Playlist.id.desc()).limit(1)
    )
    return {**item_out(chart, len(tracks), covers, load_banners(db)), "folder": chart.folder_path, "tracks": tracks, "shared_playlist_id": shared}


class SharedIn(BaseModel):
    name: str | None = Field(None, max_length=200)


@router.post("/charts/{chart_id}/shared-playlist", status_code=201)
def make_shared(chart_id: int, body: SharedIn, user: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """A shared playlist of the chart's or theme's songs as they are now, in its order: everyone sees it
    on the charts & themes page and at home. {"id"} of the new list."""
    chart = get_chart_row(db, chart_id)
    songs = db.scalars(select(Track).where(Track.chart_id == chart.id, present_tracks()))
    ids = [t.id for t in sorted(songs, key=chart_order)]
    if not ids:
        raise api_error(404, "not_found")
    playlist = Playlist(user_id=user.id, name=(body.name or "").strip() or chart.title[:200], is_shared=True, chart_id=chart.id)
    db.add(playlist)
    db.flush()
    db.add_all(PlaylistTrack(playlist_id=playlist.id, track_id=t, position=i) for i, t in enumerate(ids))
    db.commit()
    return {"id": playlist.id}


@router.get("/charts/{chart_id}/folder-banner")
def folder_banner(chart_id: int, _: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    chart = get_chart_row(db, chart_id)
    path = settings.music_dir / chart.banner_file if chart.banner_file else None
    if path is None or ".." in chart.banner_file.split("/") or not path.is_file():
        raise api_error(404, "not_found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/banners/{banner_id}")
def get_banner(banner_id: int, _: User = Depends(current_user)):
    path = ai_banner.banner_file(banner_id)
    if not path.is_file():
        raise api_error(404, "not_found")
    # the URL carries ?v=<updated_at>, so a new image gets a new URL
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000"})


# ---- admin: AI banners ----


@router.get("/admin/banners/status")
def banner_status(_: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    without = 0
    banners = load_banners(db)
    for chart in db.scalars(select(Chart).where(chart_count() > 0)):
        if banner_out(chart, banners) is None:
            without += 1
    return {
        "provider": ai_banner.provider(),
        "model": ai_banner.model(),
        "configured": ai_banner.configured(),
        "banners": len(banners),
        "without_banner": without,
    }


def draft_prompt(db: Session, chart: Chart) -> str:
    songs = db.execute(
        select(Track.artist_text, Track.title)
        .where(Track.chart_id == chart.id, present_tracks())
        .order_by(Track.chart_position.nulls_last(), Track.file_path)
        .limit(10)
    ).all()
    if chart.kind == "chart":
        what = f'the music chart "{chart.title}"' + (f" from {chart.source}" if chart.source else "")
    else:
        what = f'the music playlist "{chart.title}"' + (f" (category: {chart.source})" if chart.source else "")
    lines = "\n".join(f"- {a} - {t}" if a else f"- {t}" for a, t in songs)
    return (
        f"Wide 16:9 banner artwork for {what} in a personal music streaming app.\n"
        f"Songs in it include:\n{lines}\n\n"
        "Capture the mood and era of these songs with an evocative, modern, high-quality illustration or photo-like scene. "
        "Do not draw any text, letters, numbers, logos or watermarks. "
        "Do not depict recognizable real people. "
        "Keep the lower-left area darker and simple so a title can be placed over it."
    )


@router.get("/admin/banners/prompt")
def banner_prompt(chart_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    chart = get_chart_row(db, chart_id)
    return {"prompt": draft_prompt(db, chart)}


class GenerateIn(BaseModel):
    chart_id: int
    prompt: str = Field(default="", max_length=4000)
    use_covers: bool = True
    # edit an image instead of starting over: a candidate token or an applied banner id
    edit_candidate: str | None = Field(default=None, max_length=64)
    edit_banner: int | None = None
    instruction: str = Field(default="", max_length=2000)


REFERENCE_NOTE = (
    "\n\nThe attached album covers are only a reference for colors and mood. "
    "Do not copy them, do not show them as album covers, and do not reproduce any text in them."
)
EDIT_PROMPT = (
    "Edit the attached banner image: {instruction}\n"
    "Keep it a wide 16:9 banner with no text, letters, logos or watermarks."
)


@router.post("/admin/banners/generate", status_code=202)
def generate_banner(body: GenerateIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    chart = get_chart_row(db, body.chart_id)
    if body.edit_candidate or body.edit_banner is not None:
        if body.edit_candidate:
            source = ai_banner.candidate_file(body.edit_candidate)
        else:
            source = ai_banner.banner_file(body.edit_banner)
        if not body.instruction.strip() or source is None or not source.is_file():
            raise api_error(400, "validation")
        prompt, images = EDIT_PROMPT.format(instruction=body.instruction.strip()), [source.read_bytes()]
    else:
        prompt = body.prompt.strip() or draft_prompt(db, chart)
        images = []
        if body.use_covers:
            for album_id in cover_albums(db, [chart.id]).get(chart.id, [])[:4]:
                ref = ai_banner.reference_jpeg(cover_file(album_id, "large"), 512)
                if ref:
                    images.append(ref)
            if images:
                prompt += REFERENCE_NOTE
    try:
        job = ai_banner.start(prompt, images)
    except ai_banner.AiError as exc:
        raise api_error(409 if str(exc) == "ai_busy" else 400, str(exc)) from None
    return {"job": job, "prompt": prompt}


@router.get("/admin/banners/jobs/{job_id}")
def banner_job(job_id: str, _: User = Depends(admin_user)):
    job = ai_banner.jobs.get(job_id)
    if job is None:
        raise api_error(404, "not_found")
    out = {"status": job["status"], "error": job["error"], "candidate": job["candidate"], "url": None}
    if job["candidate"]:
        out["url"] = f"/api/v1/admin/banners/candidates/{job['candidate']}"
    return out


@router.get("/admin/banners/candidates/{token}")
def get_candidate(token: str, _: User = Depends(admin_user)):
    path = ai_banner.candidate_file(token)
    if path is None or not path.is_file():
        raise api_error(404, "not_found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


class ApplyIn(BaseModel):
    chart_id: int
    candidate: str = Field(min_length=32, max_length=32)
    scope: str = Field(default="collection", pattern="^(collection|source)$")
    prompt: str = ""  # kept for reference only: cut, never rejected after the image was paid for


@router.post("/admin/banners")
def apply_banner(body: ApplyIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    chart = get_chart_row(db, body.chart_id)
    path = ai_banner.candidate_file(body.candidate)
    if path is None or not path.is_file():
        raise api_error(404, "not_found")
    if body.scope == "source" and (chart.kind != "chart" or not chart.source):
        raise api_error(400, "validation")
    key = source_key(chart.source) if body.scope == "source" else folder_key(chart)
    banner = db.scalar(select(Banner).where(Banner.key == key))
    if banner is None:
        banner = Banner(key=key)
        db.add(banner)
    banner.prompt = body.prompt[:8000]
    banner.provider = ai_banner.provider()
    banner.model = ai_banner.model()
    banner.updated_at = func.now()
    db.flush()
    settings.cover_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(path, ai_banner.banner_file(banner.id))
    bump_library(db)
    db.commit()
    db.refresh(chart)
    return {"banner": banner_out(chart, load_banners(db))}


@router.delete("/admin/banners/{banner_id}")
def delete_banner(banner_id: int, chart_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Back to the next banner in line (source banner, banner.jpg or the cover one)."""
    banner = db.get(Banner, banner_id)
    if banner is not None:
        db.delete(banner)
        bump_library(db)
        db.commit()
        ai_banner.banner_file(banner_id).unlink(missing_ok=True)
    chart = get_chart_row(db, chart_id)
    return {"banner": banner_out(chart, load_banners(db))}


LIBRARY_FOUND = 24  # of each kind


@router.get("/library/search")
def library_search(
    q: str = Query(min_length=1, max_length=100),
    _: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """The library search (a phone's library page), for the kinds the album, artist and song lists
    can't answer: genres, folders, charts and themes whose name has it, or that hold songs matching
    it (by title or artist, as the songs list searches), with how many such songs each holds."""
    songs = search_index.matches(Track.search_text, q, Track.artist_id, db)
    named = like(q.strip())

    genre_rows = db.execute(
        select(Genre.id, Genre.name, func.count(Track.id).filter(*songs).label("n"), func.count(Track.id))
        .join(TrackGenre, TrackGenre.genre_id == Genre.id)
        .join(Track, (Track.id == TrackGenre.track_id) & listed_tracks())
        .group_by(Genre.id)
        .having(or_(func.count(Track.id).filter(*songs) > 0, Genre.name.ilike(named)))
        .order_by(literal_column("n").desc(), func.lower(Genre.name))
        .limit(LIBRARY_FOUND)
    ).all()
    genres = [{"id": i, "name": n, "match_count": m, "track_count": c} for i, n, m, c in genre_rows]

    # a folder: where songs are (their file's folder, as on the folders page: NFC)
    is_nfc = Track.file_path.op("IS", is_comparison=True)(literal_column("NFC NORMALIZED"))
    path = case((is_nfc, Track.file_path), else_=func.normalize(Track.file_path, text("NFC")))
    folder = func.regexp_replace(path, "/[^/]*$", "")
    folder_rows = db.execute(
        select(folder.label("f"), func.count().filter(*songs).label("n"), func.count(), func.min(Track.album_id).filter(Album.cover_path.is_not(None)))
        .outerjoin(Album, Album.id == Track.album_id)
        .where(present_tracks(), func.strpos(path, "/") > 0)
        .group_by(folder)
        .having(or_(func.count().filter(*songs) > 0, func.regexp_replace(folder, "^.*/", "").ilike(named)))
        .order_by(literal_column("n").desc(), literal_column("f"))
        .limit(LIBRARY_FOUND)
    ).all()
    versions = dict(db.execute(select(Album.id, Album.cover_version).where(Album.id.in_([r[3] for r in folder_rows if r[3]]))).all())
    folders = [
        {"path": f, "name": f.rsplit("/", 1)[-1], "match_count": m, "track_count": c, "cover": {"id": a, "v": versions.get(a, 0)} if a else None}
        for f, m, c, a in folder_rows
    ]
    # the folders above them named so too ("album/아이유" over its albums' folders): first, with their sums
    want = search_index.norm(q)
    above: dict[str, dict] = {}
    for f in folders:
        parts = f["path"].split("/")[:-1]
        for i in range(len(parts), 0, -1):
            if want in search_index.norm(parts[i - 1]):
                p = "/".join(parts[:i])
                up = above.setdefault(p, {"path": p, "name": parts[i - 1], "match_count": 0, "track_count": 0, "cover": f["cover"]})
                up["match_count"] += f["match_count"]
                up["track_count"] += f["track_count"]
    folders = (list(above.values()) + folders)[:LIBRARY_FOUND]

    matched = select(Track.chart_id, func.count().label("n")).where(present_tracks(), Track.chart_id.is_not(None), *songs).group_by(Track.chart_id).subquery()
    chart_rows = db.execute(
        select(Chart, chart_count().label("total"), func.coalesce(matched.c.n, 0))
        .outerjoin(matched, matched.c.chart_id == Chart.id)
        .where(chart_count() > 0, or_(matched.c.n > 0, Chart.title.ilike(named)))
        .order_by(Chart.kind, func.coalesce(matched.c.n, 0).desc(), Chart.title.desc())
        .limit(LIBRARY_FOUND * 2)
    ).all()
    covers = cover_albums(db, [c.id for c, _, _ in chart_rows])
    banners = load_banners(db)
    charts = [{**item_out(c, n, covers, banners), "match_count": m} for c, n, m in chart_rows]
    return {"genres": genres, "folders": folders, "charts": charts}
