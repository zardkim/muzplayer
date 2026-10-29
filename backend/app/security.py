import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, UserSession

COOKIE_NAME = "muz_session"
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15

_hasher = PasswordHasher()
# used to keep timing similar when the username does not exist
_DUMMY_HASH = _hasher.hash("muzplayer-dummy-password")


def now() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def dummy_verify(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user_id: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = now() + timedelta(days=settings.session_days)
    db.execute(delete(UserSession).where(UserSession.expires_at < now()))
    db.add(UserSession(id=_token_hash(token), user_id=user_id, expires_at=expires_at))
    return token, expires_at


def delete_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.id == _token_hash(token)))


def delete_user_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))


def api_error(status: int, code: str) -> HTTPException:
    """Errors carry only a code; the frontend translates it."""
    return HTTPException(status_code=status, detail=code)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise api_error(401, "not_authenticated")
    row = db.execute(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.id == _token_hash(token), UserSession.expires_at > now())
    ).scalar_one_or_none()
    if row is None or not row.is_active:
        raise api_error(401, "not_authenticated")
    return row


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise api_error(403, "forbidden")
    return user
