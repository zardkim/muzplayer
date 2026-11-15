"""What's new: albums, audiobooks, music videos, charts and themes added since the person last
looked (the bell in the app). Counted from when they were added (created_at), per person
(User.news_seen_at), so every device of theirs agrees. The first look starts from then: a new
account, or this update, doesn't greet anyone with the whole library. The news page itself asks for
a span instead (`days`: the last week unless they pick another), the bell's count stays the new."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Album, Book, Chart, User, Video
from ..security import current_user, now
from .books import book_out, with_progress
from .collections import chart_count, cover_albums, item_out, load_banners
from .library import album_list_query, album_out, not_chart
from .videos import _listing, list_item

router = APIRouter()

SHOWN = 24  # of each kind; the counts are of all


@router.get("/me/news")
def news(
    days: int | None = Query(None, ge=1, le=366),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """What was added after news_seen_at (or in the last `days`), newest first. `until` is when this
    was looked up: marking it seen up to then (POST /me/news/seen) keeps what arrives meanwhile new."""
    until = now()
    since = until - timedelta(days=days) if days else user.news_seen_at
    if user.news_seen_at is None:
        user.news_seen_at = until
        db.commit()
    if since is None:
        return {"since": until, "until": until, "total": 0, "counts": {}, "albums": [], "books": [], "videos": [], "charts": []}

    def counted(stmt):
        return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    albums_q = album_list_query([not_chart(), Album.created_at > since])
    albums = db.execute(albums_q.order_by(Album.created_at.desc()).limit(SHOWN)).all()

    books, n_books = [], 0
    if settings.audiobook_dir is not None:
        books_conds = [Book.missing_at.is_(None), Book.created_at > since]
        n_books = db.scalar(select(func.count()).select_from(Book).where(*books_conds)) or 0
        books = [book_out(b, p) for b, p in db.execute(with_progress(user.id).where(*books_conds).order_by(Book.created_at.desc()).limit(SHOWN))]

    # someone's own additions aren't news to them
    video_conds = [Video.created_at > since, func.coalesce(Video.added_by, 0) != user.id]
    n_videos = db.scalar(select(func.count()).select_from(Video).where(*video_conds)) or 0
    videos = [list_item(r, user) for r in db.execute(_listing(user.id).where(*video_conds).order_by(Video.created_at.desc()).limit(SHOWN))]

    chart_q = select(Chart, chart_count().label("n")).where(chart_count() > 0, Chart.created_at > since)
    charts = db.execute(chart_q.order_by(Chart.created_at.desc()).limit(SHOWN)).all()
    n_kinds = dict(db.execute(select(Chart.kind, func.count()).where(chart_count() > 0, Chart.created_at > since).group_by(Chart.kind)).all())
    covers = cover_albums(db, [c.id for c, _ in charts])
    banners = load_banners(db)

    counts = {
        "albums": counted(albums_q),
        "books": n_books,
        "videos": n_videos,
        "charts": n_kinds.get("chart", 0),
        "themes": n_kinds.get("theme", 0),
    }
    return {
        "since": since,
        "until": until,
        "total": sum(counts.values()),
        "counts": counts,
        "albums": [album_out(r) for r in albums],
        "books": books,
        "videos": videos,
        "charts": [item_out(c, n, covers, banners) for c, n in charts],
    }


class SeenIn(BaseModel):
    until: datetime


@router.post("/me/news/seen")
def news_seen(body: SeenIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """Seen up to `until` (the news' own), never later than now nor back before an earlier look."""
    until = min(body.until, now())
    if user.news_seen_at is None or until > user.news_seen_at:
        user.news_seen_at = until
        db.commit()
    return {"seen_at": user.news_seen_at}
