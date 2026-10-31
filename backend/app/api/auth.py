from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import ai_banner, youtube
from ..config import SUPPORTED_LOCALES, settings
from ..db import get_db
from ..models import User
from ..security import (
    COOKIE_NAME,
    LOCK_MINUTES,
    MAX_FAILED_LOGINS,
    api_error,
    create_session,
    current_user,
    delete_session,
    dummy_verify,
    hash_password,
    needs_rehash,
    now,
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
    }


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db, scope="function")):
    user = db.execute(select(User).where(User.username == body.username.strip())).scalar_one_or_none()
    if user is None:
        dummy_verify(body.password)
        raise api_error(401, "invalid_credentials")
    if user.locked_until and user.locked_until > now():
        raise api_error(429, "account_locked")
    if not verify_password(user.password_hash, body.password):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.failed_logins = 0
            user.locked_until = now() + timedelta(minutes=LOCK_MINUTES)
        db.commit()
        raise api_error(401, "invalid_credentials")
    if not user.is_active:
        raise api_error(403, "account_disabled")

    user.failed_logins = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    start_session(db, user, response)
    return user_out(user)


def start_session(db: Session, user: User, response: Response) -> None:
    token, expires_at = create_session(db, user.id)
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        expires=expires_at,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


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


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db, scope="function")):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(db, token)
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


class HomeSection(BaseModel):
    key: str = Field(min_length=1, max_length=32)
    on: bool


class SettingsIn(BaseModel):
    record_history: bool | None = None
    home_sections: list[HomeSection] | None = Field(None, max_length=20)


@router.patch("/auth/me")
def update_me(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")):
    """This person's own settings (kept on the server, the same on every device)."""
    if body.record_history is not None:
        user.record_history = body.record_history
    if body.home_sections is not None:
        user.home_sections = [s.model_dump() for s in body.home_sections]
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
