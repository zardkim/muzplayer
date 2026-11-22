"""Mixes and smart playlists: lists of songs worked out from a user's plays, ratings and likes and
the library's tags, each time they are opened. Rules, not recommendations (plan 16.4).

Rules JSON of a smart playlist:
  {"match": "all" | "any",
   "rules": [{"field": "genre", "op": "is", "value": "발라드"}, ...],
   "sort": "random", "limit": 100,
   # made with the wizard (all optional; without them a list works as before):
   "profile": true,        # its owner's taste (users.taste, Taste below) is part of the rules
   "mix": "balanced",      # familiar songs and new ones, in a share (MIX_SHARES)
   "minutes": 120,         # as many songs as fill this long (limit still caps the count)
   "per_artist": 3,        # at most this many songs of one artist, never two in a row
   "seed": 123,            # songs like this one first (the radio's score)
   "refresh": "daily"}     # kept for a day or a week (smart_snapshots), or worked out on each open
"""

from datetime import UTC, datetime, timedelta
import random
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator
from sqlalchemy import Select, and_, case, exists, func, literal, not_, or_, select, true
from sqlalchemy.orm import Session

from .models import Album, Chart, Favorite, Genre, PlayCount, PlayHistory, Track, TrackArtist, TrackGenre, TrackRating

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
    profile: bool = False
    mix: Literal["any", "familiar", "balanced", "new"] = "any"
    minutes: int | None = Field(None, ge=10, le=1440)
    per_artist: int | None = Field(None, ge=1, le=50)
    seed: int | None = None
    refresh: Literal["open", "daily", "weekly"] = "open"


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


# ---- taste: what a user told the wizard they like (users.taste) ----

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
DECADES_ASKED = tuple(range(1950, 2030, 10))


class Taste(BaseModel):
    """Liked genres or artists (either: a song of a liked genre by another artist counts), from these
    decades, without what is left out. Empty lists ask for nothing."""

    genres: list[Text] = Field(default_factory=list, max_length=50)  # by name, any case (merges rename them)
    artists: list[int] = Field(default_factory=list, max_length=100)  # artist ids (merges move them)
    decades: list[int] = Field(default_factory=list, max_length=len(DECADES_ASKED))
    exclude_genres: list[Text] = Field(default_factory=list, max_length=50)
    exclude_artists: list[int] = Field(default_factory=list, max_length=100)
    exclude_tracks: list[int] = Field(default_factory=list, max_length=5000)  # "not in my smart playlists"
    skip_charts: bool = False  # chart and theme songs left out
    skip_recent_days: int = Field(0, ge=0, le=365)  # songs played in the last so many days left out
    max_minutes: int | None = Field(None, ge=1, le=120)  # longer songs left out

    @field_validator("decades")
    @classmethod
    def known_decades(cls, v: list[int]) -> list[int]:
        if any(d not in DECADES_ASKED for d in v):
            raise ValueError("unknown decade")
        return sorted(set(v))


def _has_genre(names: list[str]):
    return exists().where(
        TrackGenre.track_id == Track.id, TrackGenre.genre_id == Genre.id, func.lower(Genre.name).in_([n.lower() for n in names])
    )


def _by_artists(ids: list[int]):
    return or_(Track.artist_id.in_(ids), exists().where(TrackArtist.track_id == Track.id, TrackArtist.artist_id.in_(ids)))


def taste_conditions(taste: Taste) -> list:
    """The taste as conditions on a track query with the album and the user's marks joined (with_user_marks)."""
    conds = []
    liked = ([_has_genre(taste.genres)] if taste.genres else []) + ([_by_artists(taste.artists)] if taste.artists else [])
    if liked:
        conds.append(or_(*liked))
    if taste.decades:
        conds.append(or_(*(Album.year.between(d, d + 9) for d in taste.decades)))
    if taste.exclude_genres:
        conds.append(not_(_has_genre(taste.exclude_genres)))
    if taste.exclude_artists:
        conds.append(not_(_by_artists(taste.exclude_artists)))
    if taste.exclude_tracks:
        conds.append(Track.id.not_in(taste.exclude_tracks))
    if taste.skip_charts:
        conds.append(Track.chart_id.is_(None))
    if taste.skip_recent_days:
        conds.append(or_(PlayCount.last_played_at.is_(None), PlayCount.last_played_at < _ago(taste.skip_recent_days)))
    if taste.max_minutes:
        conds.append(or_(Track.duration.is_(None), Track.duration <= taste.max_minutes * 60))
    return conds


# ---- smart playlists: the songs, in order ----

# familiar songs : new ones
MIX_SHARES = {"familiar": (0.8, 0.2), "balanced": (0.5, 0.5), "new": (0.2, 0.8)}
UNKNOWN_LENGTH = 210  # seconds, for a song without one (a time limit still adds up)
MAX_FETCH = 2000


def _familiar(user_id: int):
    """Songs this person knows: liked, ★4 and up, or played three times or more."""
    liked = exists().where(Favorite.user_id == user_id, Favorite.track_id == Track.id)
    return or_(liked, func.coalesce(TrackRating.rating, 0) >= 8, func.coalesce(PlayCount.plays, 0) >= 3)


def _new(user_id: int):
    """The rest: songs this person does not know as well."""
    return not_(_familiar(user_id))


def smart_where(rules: Rules, user_id: int, taste: Taste | None) -> list:
    """Every condition of a smart playlist (its rules, its owner's taste), on a track query with
    the album and the user's marks joined; listed songs only."""
    from .api.library import listed_tracks

    conds = [_condition(r, user_id) for r in rules.rules]
    where = [listed_tracks(), (and_(*conds) if rules.match == "all" else or_(*conds)) if conds else true()]
    if rules.profile and taste is not None:
        where += taste_conditions(taste)
    return where


def _base(user_id: int) -> Select:
    query = select(Track.id, Track.artist_id, Track.duration).outerjoin(Album, Album.id == Track.album_id)
    return with_user_marks(query, user_id)


def matching_count(db: Session, rules: Rules, user_id: int, taste: Taste | None) -> int:
    """How many songs the conditions let in, before the share, the limits and the order."""
    query = _base(user_id).where(*smart_where(rules, user_id, taste))
    return db.scalar(select(func.count()).select_from(query.subquery())) or 0


def smart_ids(db: Session, rules: Rules, user_id: int, taste: Taste | None) -> list[int]:
    """The ids of a smart playlist's songs, in order."""
    where = smart_where(rules, user_id, taste)
    seed = db.get(Track, rules.seed) if rules.seed else None
    if seed is not None:
        seed_year = db.scalar(select(Album.year).where(Album.id == seed.album_id)) if seed.album_id else None
        order = [_similarity(seed, seed_year, user_id).desc()]
        where = [*where, Track.id != seed.id]
    else:
        order = _order(rules.sort)
    shaped = rules.mix != "any" or rules.per_artist or rules.minutes
    fetch = min(MAX_FETCH, rules.limit * 4) if shaped else rules.limit
    if rules.mix == "any":
        pools = [db.execute(_base(user_id).where(*where).order_by(*order).limit(fetch)).all()]
        shares: tuple[float, ...] = (1.0,)
    else:
        pools = [
            db.execute(_base(user_id).where(*where, part).order_by(*order).limit(fetch)).all()
            for part in (_familiar(user_id), _new(user_id))
        ]
        shares = MIX_SHARES[rules.mix]
    picked = _pick(pools, shares, rules)
    if rules.mix != "any" and seed is None and rules.sort == "random":
        random.shuffle(picked)  # (taken in turns from the two pools: not in a pattern)
    if rules.per_artist:
        picked = _spread(picked)
    return [row.id for row in picked]


def _pick(pools: list[list], shares: tuple[float, ...], rules: Rules) -> list:
    """Takes from each pool in its share (a pool that runs out leaves its place to the others),
    up to the limit, the time and the songs per artist."""
    taken: list = []
    counts = [0] * len(pools)
    places = [0] * len(pools)
    per_artist: dict[int | None, int] = {}
    seen: set[int] = set()
    seconds = 0.0
    while len(taken) < rules.limit and (rules.minutes is None or seconds < rules.minutes * 60):
        open_pools = [i for i in range(len(pools)) if places[i] < len(pools[i])]
        if not open_pools:
            break
        i = min(open_pools, key=lambda k: counts[k] / shares[k] if shares[k] else float("inf"))
        row = pools[i][places[i]]
        places[i] += 1
        if row.id in seen:
            continue
        if rules.per_artist and row.artist_id is not None and per_artist.get(row.artist_id, 0) >= rules.per_artist:
            continue
        seen.add(row.id)
        per_artist[row.artist_id] = per_artist.get(row.artist_id, 0) + 1
        counts[i] += 1
        taken.append(row)
        seconds += row.duration or UNKNOWN_LENGTH
    return taken


def _spread(rows: list) -> list:
    """The same order, but no artist twice in a row where another song can go between."""
    rows = list(rows)
    for i in range(1, len(rows)):
        if rows[i].artist_id is not None and rows[i].artist_id == rows[i - 1].artist_id:
            j = next((k for k in range(i + 1, len(rows)) if rows[k].artist_id != rows[i - 1].artist_id), None)
            if j is not None:
                rows[i], rows[j] = rows[j], rows[i]
    return rows


# ---- mixes: ready-made lists every user has ----

DECADES = (1990, 2000, 2010, 2020)
MIX_KEYS = ("random", "on-repeat", "top", "rewind", "top-rated", "unplayed", "recent") + tuple(
    f"{d}s" for d in DECADES
)


# kept out of the random mix and the home stations that pick from the whole library (a listener
# asks for these on their own): kids music and CCM, by genre, by theme (its category or title) or
# by a folder named after them
NOT_EVERYDAY = r"kids|children|동요|어린이|키즈|ccm|hillsong|힐송|찬양|찬송|워십|worship|gospel|가스펠"
NOT_EVERYDAY_DIR = r"(^|/)(kids( music)?|children'?s? music|동요|어린이 ?동요|키즈|ccm|hillsong|힐송|찬양|찬송가?|워십|worship)/"


def everyday():
    """Songs fit for any mix: not kids music, not CCM."""
    return and_(
        not_(Track.file_path.op("~*")(NOT_EVERYDAY_DIR)),
        not_(exists().where(TrackGenre.track_id == Track.id, TrackGenre.genre_id == Genre.id,
                            Genre.name.op("~*")(NOT_EVERYDAY))),
        not_(exists().where(Chart.id == Track.chart_id, Chart.kind == "theme",
                            or_(Chart.source.op("~*")(NOT_EVERYDAY), Chart.title.op("~*")(NOT_EVERYDAY)))),
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
    if rules is None:
        return None
    query = apply_rules(query, rules, user_id)
    return query.where(everyday()) if key == "random" else query


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
        if key == "random":
            q = q.where(everyday())
    rows = db.execute(q).all()
    covers: list[dict] = []
    for _, album_id, cover_path, version in rows:
        if cover_path and album_id not in [c["id"] for c in covers]:
            covers.append({"id": album_id, "v": version})
            if len(covers) == 4:
                break
    return len(rows), covers


# ---- radio: songs like a seed song, for "radio" and for playing on when the queue runs out ----

def _shares_genre(seed: Track):
    genre_ids = select(TrackGenre.genre_id).where(TrackGenre.track_id == seed.id).scalar_subquery()
    return exists().where(TrackGenre.track_id == Track.id, TrackGenre.genre_id.in_(genre_ids))


def _similarity(seed: Track, seed_year: int | None, user_id: int):
    """How like the seed a song is (higher: more): same artist, a shared genre, a year within five,
    this user's likes and stars, and some randomness. Needs the album and the user's marks joined."""
    liked = exists().where(Favorite.user_id == user_id, Favorite.track_id == Track.id)
    return (
        (case((Track.artist_id == seed.artist_id, 2), else_=0) if seed.artist_id is not None else literal(0))
        + case((_shares_genre(seed), 3), else_=0)
        + (case((func.abs(Album.year - seed_year) <= 5, 1), else_=0) if seed_year else literal(0))
        + case((TrackRating.rating >= 8, 1), else_=0)
        + case((liked, 1), else_=0)
        + func.random() * 4
    )


def radio_ids(
    seed: Track, seed_year: int | None, user_id: int, exclude: list[int], limit: int, related: bool = True
) -> Select:
    """The ids of songs like the seed, best first (the caller then loads just those: scoring only
    ids keeps the per-song extras of track_query off the thousands of candidates). Scores each listed song: same artist, a shared genre,
    a year within five, and this user's own likes and stars; randomness keeps it from repeating
    itself and mixes other artists in. related: only songs sharing the artist or a genre with the seed
    (the caller asks again without it when that finds nothing, e.g. an untagged seed)."""
    from .api.library import listed_tracks

    links = [_shares_genre(seed)]
    if seed.artist_id is not None:
        links.append(Track.artist_id == seed.artist_id)
    # (the year only adds to the score: as a link it would let in most of the library and be slow)
    score = _similarity(seed, seed_year, user_id)
    conds = [listed_tracks(), Track.id != seed.id] + ([or_(*links)] if related else [])
    if exclude:
        conds.append(Track.id.not_in(exclude))
    query = select(Track.id).outerjoin(Album, Album.id == Track.album_id)
    return with_user_marks(query, user_id).where(*conds).order_by(score.desc()).limit(limit)
