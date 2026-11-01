import json
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import ai_banner, ai_playlist, appconf, transcode, youtube
from ..config import SUPPORTED_LOCALES, settings
from ..db import get_db
from ..models import User
from ..security import (
    COOKIE_NAME,
    LOCK_MINUTES,
    MAX_FAILED_LOGINS,
    MAX_OTHERS,
    OTHERS_COOKIE,
    api_error,
    create_session,
    current_user,
    delete_session,
    dummy_verify,
    hash_password,
    needs_rehash,
    now,
    session_user,
    verify_password,
)

router = APIRouter()


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "record_history": user.record_history,
        "home_sections": user.home_sections,
        "prefs": user.prefs,
        "pending": user.pending,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def has_users(db: Session) -> bool:
    return bool(db.scalar(select(func.count()).select_from(User)))


@router.get("/config")
def get_config(db: Session = Depends(get_db, scope="function")):
    locale = settings.default_locale if settings.default_locale in SUPPORTED_LOCALES else "ko"
    return {
        "default_locale": locale,
        "locales": list(SUPPORTED_LOCALES),
        "version": settings.version,
        "audiobooks": settings.audiobook_dir is not None,
        "ai_banners": ai_banner.configured(),
        "youtube_search": youtube.configured(),  # in-app video search; without it links are pasted
        "needs_setup": not has_users(db),  # a fresh install: the login page makes the first (admin) account
        "transcode": transcode.available(),  # stream quality, WMA/APE, levelling on the server
        "ai_playlists": ai_playlist.configured(),  # the AI key an admin set for banners
        "signup": appconf.signup_mode(),  # off | approval | open (admin page)
    }


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    add: bool = False  # another account on this device: the one signed in now stays (user switching)


def check_password(db: Session, user: User, password: str) -> None:
    """Raises on a wrong password, counting it toward the lockout (login and switching alike)."""
    if user.locked_until and user.locked_until > now():
        raise api_error(429, "account_locked")
    if not verify_password(user.password_hash, password):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.failed_logins = 0
            user.locked_until = now() + timedelta(minutes=LOCK_MINUTES)
        db.commit()
        raise api_error(401, "invalid_credentials")
    user.failed_logins = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db, scope="function")):
    user = db.execute(select(User).where(User.username == body.username.strip())).scalar_one_or_none()
    if user is None:
        dummy_verify(body.password)
        raise api_error(401, "invalid_credentials")
    check_password(db, user, body.password)
    if not user.is_active:
        raise api_error(403, "pending_approval" if user.pending else "account_disabled")
    others = others_on_device(db, request)
    current = request.cookies.get(COOKIE_NAME)
    signed_in = session_user(db, current) if body.add and current else None
    if signed_in is not None:
        others.insert(0, (current, signed_in))
    start_session(db, user, response)
    set_others(response, [t for t, u in others if u.id != user.id])
    return user_out(user)


def _cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        name,
        value,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def start_session(db: Session, user: User, response: Response) -> None:
    token, _ = create_session(db, user.id)
    user.last_login_at = now()
    db.commit()
    _cookie(response, COOKIE_NAME, token)


# ---- user switching ----
# Family members on one device: accounts signed in here ("add account" on the login page) are kept
# in a second HttpOnly cookie and switched to without signing in again. Switching into an admin
# account asks for its password (with the login lockout), so a shared phone doesn't hand out admin.


def others_on_device(db: Session, request: Request) -> list[tuple[str, User]]:
    """(token, user) of the other accounts signed in on this device that are still valid: not the
    one signed in now, one per user, at most MAX_OTHERS."""
    current = request.cookies.get(COOKIE_NAME)
    active = session_user(db, current) if current else None
    seen = {active.id} if active else set()
    found: list[tuple[str, User]] = []
    for token in (request.cookies.get(OTHERS_COOKIE) or "").split("."):
        if not token or len(found) >= MAX_OTHERS:
            continue
        user = session_user(db, token)
        if user is not None and user.id not in seen:
            seen.add(user.id)
            found.append((token, user))
    return found


def set_others(response: Response, tokens: list[str]) -> None:
    if tokens:
        _cookie(response, OTHERS_COOKIE, ".".join(tokens[:MAX_OTHERS]))
    else:
        response.delete_cookie(OTHERS_COOKIE, path="/")


def account_out(user: User) -> dict:
    return {"id": user.id, "username": user.username, "display_name": user.display_name or user.username, "is_admin": user.is_admin}


@router.get("/auth/accounts")
def accounts(request: Request, response: Response, _: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """The other accounts signed in on this device (the cookie loses ones that ended)."""
    others = others_on_device(db, request)
    set_others(response, [t for t, _ in others])
    return [account_out(u) for _, u in others]


class SwitchIn(BaseModel):
    user_id: int
    password: str | None = Field(None, max_length=256)  # needed for an admin account


@router.post("/auth/switch")
def switch(body: SwitchIn, request: Request, response: Response, db: Session = Depends(get_db, scope="function")):
    others = others_on_device(db, request)
    match = next(((t, u) for t, u in others if u.id == body.user_id), None)
    if match is None:
        raise api_error(404, "not_found")
    token, user = match
    if user.is_admin:
        if not body.password:
            raise api_error(403, "password_required")
        check_password(db, user, body.password)
        db.commit()
    current = request.cookies.get(COOKIE_NAME)
    rest = [t for t, u in others if u.id != user.id]
    if current and session_user(db, current) is not None:
        rest.insert(0, current)
    _cookie(response, COOKIE_NAME, token)
    set_others(response, rest)
    return user_out(user)


class SetupIn(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=256)


@router.post("/auth/setup", status_code=201)
def setup(body: SetupIn, response: Response, db: Session = Depends(get_db, scope="function")):
    """The first account, made from the login page of a fresh install, is the admin. Once any
    account exists this is closed; more accounts are added on the admin page."""
    db.execute(text("LOCK TABLE users IN EXCLUSIVE MODE"))  # two first visitors: only one wins
    if has_users(db):
        raise api_error(409, "already_set_up")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.username,
        is_admin=True,
    )
    db.add(user)
    db.flush()
    start_session(db, user, response)
    return user_out(user)


# ---- sign-up (when an admin turned it on: open, or each account approved first) ----
class SignupIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field("", max_length=100)


SIGNUPS_PER_HOUR = 5  # from one address: a public page shouldn't be a way to fill the user table
_signups: dict[str, list[float]] = {}


def _signup_allowed(ip: str) -> bool:
    cutoff = time.time() - 3600
    recent = [t for t in _signups.get(ip, []) if t > cutoff]
    _signups[ip] = recent
    if len(recent) >= SIGNUPS_PER_HOUR:
        return False
    recent.append(time.time())
    return True


@router.post("/auth/signup", status_code=201)
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db, scope="function")):
    """A new (non-admin) account. Open: signed in at once. Approval: it waits for an admin
    ({"pending": true}) and can't log in until approved."""
    mode = appconf.signup_mode()
    if mode == "off" or not has_users(db):
        raise api_error(403, "signup_closed")
    if not _signup_allowed(request.client.host if request.client else "?"):
        raise api_error(429, "too_many_signups")
    if db.scalar(select(User.id).where(func.lower(User.username) == body.username.lower())) is not None:
        raise api_error(409, "username_taken")
    pending = mode == "approval"
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip() or body.username,
        is_active=not pending,
        pending=pending,
    )
    db.add(user)
    db.flush()
    if pending:
        db.commit()
        return {"pending": True}
    start_session(db, user, response)
    return user_out(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db, scope="function")):
    """Signs this account out. Another account signed in on this device takes over, if there is
    one that needs no password (not an admin): {"user": that user or null}. Admin accounts stay
    listed for signing in again."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(db, token)
        db.commit()
    others = others_on_device(db, request)
    heir = next(((t, u) for t, u in others if not u.is_admin), None)
    if heir is not None:
        _cookie(response, COOKIE_NAME, heir[0])
        set_others(response, [t for t, _ in others if t != heir[0]])
        return {"user": user_out(heir[1])}
    response.delete_cookie(COOKIE_NAME, path="/")
    set_others(response, [t for t, _ in others])
    return {"user": None}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


class HomeSection(BaseModel):
    key: str = Field(min_length=1, max_length=32)
    on: bool


class SettingsIn(BaseModel):
    record_history: bool | None = None
    home_sections: list[HomeSection] | None = Field(None, max_length=20)
    prefs: dict | None = None  # the app's settings as a whole (it knows their shape)

    @model_validator(mode="after")
    def small(self):
        if self.prefs is not None and len(json.dumps(self.prefs)) > 20_000:
            raise ValueError("prefs too large")
        return self


@router.patch("/auth/me")
def update_me(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """This person's own settings (kept on the server, the same on every device)."""
    if body.record_history is not None:
        user.record_history = body.record_history
    if body.home_sections is not None:
        user.home_sections = [s.model_dump() for s in body.home_sections]
    if body.prefs is not None:
        user.prefs = body.prefs
    db.commit()
    return user_out(user)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


@router.put("/auth/password", status_code=204)
def change_password(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    if not verify_password(user.password_hash, body.current_password):
        raise api_error(400, "wrong_password")
    user.password_hash = hash_password(body.new_password)
    db.commit()
