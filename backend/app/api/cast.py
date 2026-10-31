"""Chromecast: the Cast device fetches songs and covers itself, without the login cookie, so the
browser asks here for signed links (HMAC over user, item, quality and expiry, CAST_TTL long).
A link works only for what it was made for, until it expires and while its user stays active.

Songs a Cast device may not play (WMA, APE, AIFF, above 96 kHz) are converted to MP3 320, and
always finished first (whole=1): a receiver can't play a conversion that is still being written.
"""

import hashlib
import hmac
import secrets
import time
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import transcode
from ..cache import image_response
from ..config import settings
from ..db import get_db
from ..models import Album, Track, User
from ..scanner import cover_file
from ..security import api_error, current_user
from .library import AUDIO_TYPES, serve_track

router = APIRouter()

CAST_TTL = 12 * 3600
CONVERT = {"wma", "ape", "aif", "aiff"}
OPEN = {"Access-Control-Allow-Origin": "*"}  # some receivers ask with CORS
_secret: bytes | None = None


def secret() -> bytes:
    """Kept in CONF_DIR/cast_secret (readable by the app only); made on first use."""
    global _secret
    if _secret is None:
        path = settings.conf_dir / "cast_secret"
        if not path.exists():
            path.write_text(secrets.token_hex(32))
            path.chmod(0o600)
        _secret = path.read_text().strip().encode()
    return _secret


def sign(*parts: object) -> str:
    return hmac.new(secret(), ":".join(map(str, parts)).encode(), hashlib.sha256).hexdigest()


def check(db: Session, user_id: int, exp: int, sig: str, *parts: object) -> None:
    if exp < time.time() or not hmac.compare_digest(sig, sign(user_id, exp, *parts)):
        raise api_error(403, "forbidden")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise api_error(403, "forbidden")


class LinksIn(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=500)


@router.post("/cast/links")
def links(body: LinksIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """Signed song and cover links (paths: the browser adds its own address) for the given songs."""
    exp = int(time.time()) + CAST_TTL
    rows = db.execute(
        select(Track.id, Track.format, Track.sample_rate, Track.album_id, Album.cover_version, Album.cover_path)
        .outerjoin(Album, Album.id == Track.album_id)
        .where(Track.id.in_(body.track_ids), Track.missing_at.is_(None))
    ).all()
    out = {}
    for tid, fmt, rate, album_id, cover_v, cover_path in rows:
        convert = transcode.available() and (fmt in CONVERT or (rate or 0) > 96000)
        quality = "320" if convert else "orig"
        src = f"/api/v1/cast/tracks/{tid}/stream?quality={quality}&u={user.id}&exp={exp}&sig={sign(user.id, exp, 'track', tid, quality)}"
        cover = None
        if album_id and cover_path:
            cover = f"/api/v1/cast/albums/{album_id}/cover?v={cover_v}&u={user.id}&exp={exp}&sig={sign(user.id, exp, 'cover', album_id)}"
        out[tid] = {"src": src, "type": "audio/mpeg" if convert else AUDIO_TYPES.get(fmt, "audio/mpeg"), "cover": cover}
    return out


@router.get("/cast/tracks/{track_id}/stream")
def cast_stream(
    track_id: int,
    request: Request,
    u: int,
    exp: int,
    sig: str = Query(max_length=64),
    quality: Literal["orig", "320"] = "orig",
    db: Session = Depends(get_db, scope="function"),
):
    check(db, u, exp, sig, "track", track_id, quality)
    res = serve_track(db, track_id, request, quality, "off", whole=True)
    res.headers.update(OPEN)
    return res


@router.get("/cast/albums/{album_id}/cover")
def cast_cover(
    album_id: int, request: Request, u: int, exp: int, sig: str = Query(max_length=64), v: int | None = None,
    db: Session = Depends(get_db, scope="function"),
):
    check(db, u, exp, sig, "cover", album_id)
    path = cover_file(album_id, "large")
    if not path.exists():
        raise api_error(404, "not_found")
    res = image_response(request, path, versioned=v is not None)
    res.headers.update(OPEN)
    return res
