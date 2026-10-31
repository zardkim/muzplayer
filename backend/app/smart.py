"""Mixes and smart playlists: lists of songs worked out from a user's plays, ratings and likes and
the library's tags, each time they are opened. Rules, not recommendations (plan 16.4).

Rules JSON of a smart playlist:
  {"match": "all" | "any",
   "rules": [{"field": "genre", "op": "is", "value": "발라드"}, ...],
   "sort": "random", "limit": 100}
"""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Select, and_, case, exists, func, literal, not_, or_, select, true
from sqlalchemy.orm import Session

from .models import Album, Chart, Favorite, Genre, PlayCount, PlayHistory, Track, TrackGenre, TrackRating

MAX_LIMIT = 500

# ---- smart playlist rules ----

FIELDS = {
    # field: allowed ops
    "genre": ("is", "is_not"),
    "artist": ("contains", "not_contains"),
    "year": ("between",),
    "rating": ("gte", "lte", "none"),
    "favorite": ("is",),
    "plays": ("gte", "lte"),
    "last_played": ("within_days", "not_within_days"),
    "added": ("within_days",),
    "folder": ("is", "is_not"),
    "duration": ("gte", "lte"),  # seconds
}
FOLDERS = ("album", "compilation", "soundtrack", "chart", "theme")
SORTS = ("random", "plays", "recent", "title", "rating", "last_played")


class Rule(BaseModel):
    field: Literal["genre", "artist", "year", "rating", "favorite", "plays", "last_played", "added", "folder", "duration"]
    op: str
    value: str | int | float | bool | list[int] | None = None

    @model_validator(mode="after")
    def check(self):
        if self.op not in FIELDS[self.field]:
            raise ValueError(f"op {self.op} not allowed for {self.field}")
        v = self.value
        if self.field in ("genre", "artist"):
            if not isinstance(v, str) or not v.strip() or len(v) > 200:
                raise ValueError("text value required")
        elif self.field == "year":
            if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v)):
                raise ValueError("year needs [from, to]")
        elif self.field == "favorite":
            if not isinstance(v, bool):
                raise ValueError("true or false")
        elif self.field == "folder":
            if v not in FOLDERS:
                raise ValueError("unknown folder kind")
        elif self.field == "rating" and self.op != "none":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.5 <= v <= 5 or (v * 2) % 1:
                raise ValueError("stars 0.5-5 in halves")
        elif not (self.field == "rating" and self.op == "none"):
            if not isinstance(v, int) or isinstance(v, bool) or v < 0 or v > 100_000:
                raise ValueError("number required")
        return self


class Rules(BaseModel):
    match: Literal["all", "any"] = "all"
    rules: list[Rule] = Field(default_factory=list, max_length=20)
    sort: Literal["random", "plays", "recent", "title", "rating", "last_played"] = "random"
    limit: int = Field(100, ge=1, le=MAX_LIMIT)


def _ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _condition(rule: Rule, user_id: int):
    v, op = rule.value, rule.op
    rating = TrackRating.rating
    plays = func.coalesce(PlayCount.plays, 0)
    match rule.field:
        case "genre":
            has = exists().where(
                TrackGenre.track_id == Track.id, TrackGenre.genre_id == Genre.id, func.lower(Genre.name) == v.strip().lower()
            )
            return has if op == "is" else not_(has)
        case "artist":
            from .api.library import like  # same escaping as search

            cond = Track.artist_text.ilike(like(v.strip()))
            return cond if op == "contains" else not_(cond)
        case "year":
            lo, hi = sorted(v)
            return Album.year.between(lo, hi)
        case "rating":
            if op == "none":
                return rating.is_(None)
            return rating >= v * 2 if op == "gte" else rating <= v * 2  # stored in half stars
        case "favorite":
            liked = exists().where(Favorite.user_id == user_id, Favorite.track_id == Track.id)
            return liked if v else not_(liked)
        case "plays":
            return plays >= v if op == "gte" else plays <= v
        case "last_played":
            recent = PlayCount.last_played_at >= _ago(v)
            # never played counts as "not within"
            return recent if op == "within_days" else or_(PlayCount.last_played_at.is_(None), not_(recent))
        case "added":
            return Track.created_at >= _ago(v)
        case "folder":
            cond = {
                "album": Album.kind.in_(("album", "unofficial")),
                "compilation": Album.kind == "compilation",
                "soundtrack": Album.kind == "soundtrack",
                "chart": exists().where(Chart.id == Track.chart_id, Chart.kind == "chart"),
                "theme": exists().where(Chart.id == Track.chart_id, Chart.kind == "theme"),
            }[v]
            return cond if op == "is" else not_(cond)
        case "duration":
            return Track.duration >= v if op == "gte" else Track.duration <= v
    raise ValueError(rule.field)


def _order(sort: str):
    return {
        "random": [func.random()],
        "plays": [func.coalesce(PlayCount.plays, 0).desc(), Track.id],
        "recent": [Track.created_at.desc(), Track.id.desc()],
        "title": [func.lower(Track.title), Track.id],
        "rating": [TrackRating.rating.desc().nulls_last(), func.random()],
        "last_played": [PlayCount.last_played_at.desc().nulls_last(), Track.id],
    }[sort]


def with_user_marks(query: Select, user_id: int) -> Select:
    """Joins this user's play count and rating, which rules and sorts refer to."""
    return query.outerjoin(PlayCount, and_(PlayCount.track_id == Track.id, PlayCount.user_id == user_id)).outerjoin(
        TrackRating, and_(TrackRating.track_id == Track.id, TrackRating.user_id == user_id)
    )


def apply_rules(query: Select, rules: Rules, user_id: int) -> Select:
    """query: a track query (track_query) with the album joined; listed songs only."""
    from .api.library import listed_tracks

    conds = [_condition(r, user_id) for r in rules.rules]
    where = (and_(*conds) if rules.match == "all" else or_(*conds)) if conds else true()
    return with_user_marks(query, user_id).where(listed_tracks(), where).order_by(*_order(rules.sort)).limit(rules.limit)


# ---- mixes: ready-made lists every user has ----

DECADES = (1990, 2000, 2010, 2020)
MIX_KEYS = ("random", "on-repeat", "top", "rewind", "top-rated", "unplayed", "recent") + tuple(
    f"{d}s" for d in DECADES
)


def mix_rules(key: str) -> Rules | None:
    """Most mixes are smart playlists with fixed rules; on-repeat counts recent plays instead."""
    match key:
        case "random":
            return Rules(sort="random", limit=100)
        case "top":
            return Rules(rules=[Rule(field="plays", op="gte", value=1)], sort="plays", limit=100)
        case "rewind":
            return Rules(
                rules=[Rule(field="plays", op="gte", value=5), Rule(field="last_played", op="not_within_days", value=60)],
                sort="plays",
                limit=50,
            )
        case "top-rated":
            return Rules(rules=[Rule(field="rating", op="gte", value=4)], sort="random", limit=100)
        case "unplayed":
            return Rules(rules=[Rule(field="plays", op="lte", value=0)], sort="random", limit=100)
        case "recent":
            return Rules(sort="recent", limit=100)
    if key.endswith("s") and key[:-1].isdigit() and int(key[:-1]) in DECADES:
        start = int(key[:-1])
        return Rules(rules=[Rule(field="year", op="between", value=[start, start + 9])], sort="random", limit=100)
    return None


def on_repeat(query: Select, user_id: int, limit: int = 50) -> Select:
    """Most played in the last 30 days, from the play history (which keeps the latest 1,000 plays)."""
    from .api.library import listed_tracks

    counts = (
        select(PlayHistory.track_id, func.count().label("n"), func.max(PlayHistory.played_at).label("last"))
        .where(PlayHistory.user_id == user_id, PlayHistory.played_at >= _ago(30))
        .group_by(PlayHistory.track_id)
        .subquery()
    )
    return (
        query.join(counts, counts.c.track_id == Track.id)
        .where(listed_tracks())
        .order_by(counts.c.n.desc(), counts.c.last.desc())
        .limit(limit)
    )


def mix_query(key: str, query: Select, user_id: int) -> Select | None:
    if key == "on-repeat":
        return on_repeat(query, user_id)
    rules = mix_rules(key)
    return apply_rules(query, rules, user_id) if rules else None


def mix_preview(db: Session, key: str, user_id: int) -> tuple[int, list[dict]]:
    """(number of songs, up to 4 covers) for a mix card, without sorting the whole library
    at random: covers come from the first few songs of an id-ordered pass."""
    base = select(Track.id, Track.album_id, Album.cover_path, Album.cover_version).outerjoin(
        Album, Album.id == Track.album_id
    )
    if key == "on-repeat":
        q = on_repeat(base, user_id)
    else:
        rules = mix_rules(key)
        if rules is None:
            return 0, []
        if rules.sort == "random":
            rules = rules.model_copy(update={"sort": "recent"})  # a stable, index-backed order for the card
        q = apply_rules(base, rules, user_id)
    rows = db.execute(q).all()
    covers: list[dict] = []
    for _, album_id, cover_path, version in rows:
        if cover_path and album_id not in [c["id"] for c in covers]:
            covers.append({"id": album_id, "v": version})
            if len(covers) == 4:
                break
    return len(rows), covers


# ---- radio: songs like a seed song, for "radio" and for playing on when the queue runs out ----

def radio_ids(
    seed: Track, seed_year: int | None, user_id: int, exclude: list[int], limit: int, related: bool = True
) -> Select:
    """The ids of songs like the seed, best first (the caller then loads just those: scoring only
    ids keeps the per-song extras of track_query off the thousands of candidates). Scores each listed song: same artist, a shared genre,
    a year within five, and this user's own likes and stars; randomness keeps it from repeating
    itself and mixes other artists in. related: only songs sharing the artist or a genre with the seed
    (the caller asks again without it when that finds nothing, e.g. an untagged seed)."""
    from .api.library import listed_tracks

    genre_ids = select(TrackGenre.genre_id).where(TrackGenre.track_id == seed.id).scalar_subquery()
    shares_genre = exists().where(TrackGenre.track_id == Track.id, TrackGenre.genre_id.in_(genre_ids))
    liked = exists().where(Favorite.user_id == user_id, Favorite.track_id == Track.id)
    links = [shares_genre]
    if seed.artist_id is not None:
        links.append(Track.artist_id == seed.artist_id)
    # (the year only adds to the score: as a link it would let in most of the library and be slow)
    score = (
        (case((Track.artist_id == seed.artist_id, 2), else_=0) if seed.artist_id is not None else literal(0))
        + case((shares_genre, 3), else_=0)
        + (case((func.abs(Album.year - seed_year) <= 5, 1), else_=0) if seed_year else literal(0))
        + case((TrackRating.rating >= 8, 1), else_=0)
        + case((liked, 1), else_=0)
        + func.random() * 4
    )
    conds = [listed_tracks(), Track.id != seed.id] + ([or_(*links)] if related else [])
    if exclude:
        conds.append(Track.id.not_in(exclude))
    query = select(Track.id).outerjoin(Album, Album.id == Track.album_id)
    return with_user_marks(query, user_id).where(*conds).order_by(score.desc()).limit(limit)
