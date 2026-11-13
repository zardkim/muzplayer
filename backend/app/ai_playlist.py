"""Playlists from a sentence ("비 오는 날 듣기 좋은 잔잔한 노래"): the AI provider an admin set up
for banners turns it into smart playlist rules over this library's own genres and artists, so
every song in the result is one the library has (nothing is made up). The rules are checked like
hand-made ones, then shown for review before they are saved.

Every family account can use it (it uses text models: a request costs a fraction of a banner),
one request at a time per person.
"""

import json
import logging
import re
import threading

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ai_banner, appconf
from .ai_banner import AiError
from .models import Album, Artist, Genre, Track, TrackGenre
from .smart import FIELDS, FOLDERS, SORTS, Rule, Rules

log = logging.getLogger(__name__)

TOP_GENRES = 150
TOP_ARTISTS = 300
GEMINI_URL = ai_banner.GEMINI_URL
OPENAI_URL = "https://api.openai.com/v1/responses"

_busy: set[int] = set()
_busy_lock = threading.Lock()

# the model fills plain strings; values are turned into the rule types below
SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "A short playlist name in the request's language"},
        "match": {"type": "string", "enum": ["all", "any"]},
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": list(FIELDS)},
                    "op": {"type": "string", "enum": sorted({op for ops in FIELDS.values() for op in ops})},
                    "value": {"type": "string"},
                },
                "required": ["field", "op", "value"],
                "additionalProperties": False,
            },
        },
        "sort": {"type": "string", "enum": list(SORTS)},
    },
    "required": ["name", "match", "rules", "sort"],
    "additionalProperties": False,
}

GUIDE = """You turn a request for a playlist into filter rules over a personal music library.
Use only the genres and artists listed below, spelled exactly as listed; never invent others.
Rules (field, op, value as a string):
- genre: is | is_not, value = one listed genre
- artist: contains | not_contains, value = one listed artist
- year: between, value = "FROM-TO" (album year, e.g. "1990-1999")
- rating: gte | lte (value "0.5".."5" stars) | none (value "")
- favorite: is, value "true" or "false" (the listener's liked songs)
- plays: gte | lte, value = play count
- last_played: within_days | not_within_days, value = days
- added: within_days, value = days since added to the library
- folder: is | is_not, value = one of: album, compilation, soundtrack, chart, theme
- duration: gte | lte, value = seconds
Use 1 to 6 rules. To combine several genres or artists use match "any" with one rule each
(do not mix them with year rules in "any"; prefer genres for moods). Sort is usually "random".
Library years: {years}.
Genres (songs): {genres}
Artists (songs): {artists}
"""


def configured() -> bool:
    return ai_banner.configured()


def library_context(db: Session) -> dict:
    genres = db.execute(
        select(Genre.name, func.count())
        .join(TrackGenre, TrackGenre.genre_id == Genre.id)
        .join(Track, Track.id == TrackGenre.track_id)
        .where(Track.missing_at.is_(None))
        .group_by(Genre.name)
        .order_by(func.count().desc())
        .limit(TOP_GENRES)
    ).all()
    artists = db.execute(
        select(Artist.name, func.count())
        .join(Track, Track.artist_id == Artist.id)
        .where(Track.missing_at.is_(None))
        .group_by(Artist.name)
        .order_by(func.count().desc())
        .limit(TOP_ARTISTS)
    ).all()
    lo, hi = db.execute(select(func.min(Album.year), func.max(Album.year)).where(Album.year > 0)).one()
    return {"genres": [(g, n) for g, n in genres], "artists": [(a, n) for a, n in artists], "years": (lo, hi)}


def _ask(prompt: str, ctx: dict) -> dict:
    system = GUIDE.format(
        years=f"{ctx['years'][0]}-{ctx['years'][1]}" if ctx["years"][0] else "unknown",
        genres=", ".join(f"{g} ({n})" for g, n in ctx["genres"]) or "none",
        artists=", ".join(f"{a} ({n})" for a, n in ctx["artists"]) or "none",
    )
    return ask_json(system, prompt, SCHEMA, "smart_playlist")


def ask_json(system: str, prompt: str, schema: dict, name: str) -> dict:
    """One answer from the set-up text model, as JSON in the given schema (also extract.py's tags)."""
    which = appconf.provider()
    key = appconf.get(f"{which}_api_key")
    if which == "openai":
        body = {
            "model": appconf.text_model("openai"),
            "input": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "text": {"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
        }
        data = ai_banner._post(OPENAI_URL, json.dumps(body).encode(), {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        texts = [c.get("text", "") for item in data.get("output", []) for c in item.get("content") or [] if c.get("type") in ("output_text", "text")]
    else:
        body = {
            "model": appconf.text_model("gemini"),
            "input": f"{system}\nRequest: {prompt}",
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
        }
        data = ai_banner._post(GEMINI_URL, json.dumps(body).encode(), {"x-goog-api-key": key, "Content-Type": "application/json"})
        texts = [
            c.get("text", "")
            for step in data.get("steps", [])
            if step.get("type") == "model_output"
            for c in step.get("content") or []
            if c.get("type") == "text"
        ]
    # the answer's last JSON object: also when wrapped in ```json fences or a sentence, or (another
    # shape of the response) in any text the response holds
    for text in [*reversed(texts), *reversed(_texts(data))]:
        found = _json_in(text)
        if found is not None:
            return found
    log.warning("ai: no JSON in the answer of %s: %s", which, json.dumps(data, ensure_ascii=False)[:800])
    raise AiError("ai_bad_response")


def _texts(node) -> list[str]:
    """Every "text" (or "output_text") string anywhere in a response, in order."""
    out: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("text", "output_text") and isinstance(v, str):
                out.append(v)
            else:
                out += _texts(v)
    elif isinstance(node, list):
        for v in node:
            out += _texts(v)
    return out


def _json_in(text: str) -> dict | None:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    for candidate in (t, t[t.find("{") : t.rfind("}") + 1] if "{" in t else ""):
        try:
            found = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    return None


def _number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def _rule(raw: dict, genres: dict[str, str], artists: dict[str, str]) -> Rule | None:
    """One rule from the model's strings, or None when it isn't usable here."""
    field, op, text = raw.get("field"), raw.get("op"), str(raw.get("value") or "").strip()
    value: object = text
    if field == "genre":
        value = genres.get(text.lower())  # only genres the library has
    elif field == "artist":
        value = artists.get(text.lower())
    elif field == "year":
        years = [int(y) for y in re.findall(r"\d{4}", text)]
        value = [years[0], years[-1]] if years else None
    elif field == "rating":
        n = _number(text)
        value = None if op == "none" else (round(n * 2) / 2 if n is not None else None)
    elif field == "favorite":
        value = text.lower() in ("true", "yes", "1")
    elif field in ("plays", "last_played", "added", "duration"):
        n = _number(text)
        value = int(n) if n is not None else None
    elif field == "folder":
        value = text.lower() if text.lower() in FOLDERS else None
    if value is None and not (field == "rating" and op == "none"):
        return None
    try:
        return Rule(field=field, op=op, value=value)
    except ValidationError:
        return None


def make(db: Session, user_id: int, prompt: str) -> dict:
    """{"name", "rules"} for a request. Raises AiError (busy, provider errors, nothing usable)."""
    if not configured():
        raise AiError("ai_not_configured")
    with _busy_lock:
        if user_id in _busy:
            raise AiError("ai_playlist_busy")
        _busy.add(user_id)
    try:
        ctx = library_context(db)
        db.commit()  # the provider can take a while: don't hold a database connection meanwhile
        out = _ask(prompt, ctx)
    finally:
        with _busy_lock:
            _busy.discard(user_id)
    genres = {g.lower(): g for g, _ in ctx["genres"]}
    artists = {a.lower(): a for a, _ in ctx["artists"]}
    rules = [r for raw in (out.get("rules") or [])[:20] if isinstance(raw, dict) and (r := _rule(raw, genres, artists))]
    if not rules:
        raise AiError("ai_no_rules")
    result = Rules(
        match=out.get("match") if out.get("match") in ("all", "any") else "all",
        rules=rules,
        sort=out.get("sort") if out.get("sort") in SORTS else "random",
        limit=100,
    )
    name = str(out.get("name") or prompt).strip()[:100] or prompt[:100]
    return {"name": name, "rules": result.model_dump()}
