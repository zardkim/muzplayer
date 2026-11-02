"""The admin's log page: sign-ins (and failed ones) and every change made on the admin page.

Written in a session of its own, so an entry stays even when the request then fails (a wrong
password). Kept for KEEP_DAYS; older entries go now and then as new ones come.
"""

import logging
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete

from .db import SessionLocal
from .models import ActivityLog, User
from .security import now

log = logging.getLogger(__name__)

KEEP_DAYS = 180


def client_ip(request: Request | None) -> str:
    # uvicorn runs with --proxy-headers: behind the NAS's proxy this is the visitor's address
    return (request.client.host if request and request.client else "")[:64]


def record(action: str, user: User | None = None, *, username: str = "", detail: str = "", request: Request | None = None) -> None:
    try:
        with SessionLocal() as db:
            entry = ActivityLog(
                user_id=user.id if user else None,
                username=(user.username if user else username)[:64],
                action=action,
                detail=detail[:300],
                ip=client_ip(request),
            )
            db.add(entry)
            db.flush()
            if entry.id % 200 == 0:
                db.execute(delete(ActivityLog).where(ActivityLog.at < now() - timedelta(days=KEEP_DAYS)))
            db.commit()
    except Exception:  # the log must never break signing in or an admin change
        log.exception("activity log")


# ---- every change on the admin page (POST/PUT/PATCH/DELETE under /api/v1/admin) ----

ADMIN_PREFIX = "/api/v1/admin/"
# body fields whose values go into the entry; others are listed by name only (passwords, API keys)
SHOWN = {"mode", "folder", "kind", "is_admin", "is_active", "username", "display_name", "ai_provider", "source", "title", "keep"}
def _target(path: str) -> str:
    """The name of what /admin/<users|artists|albums>/<id>/... changes (looked up before: a delete removes it)."""
    from .models import Album, Artist  # noqa: PLC0415 - only for the names

    parts = path[len(ADMIN_PREFIX):].split("/")
    if len(parts) < 2 or not parts[1].isdigit():
        return ""
    model, attr = {"users": (User, "username"), "artists": (Artist, "name"), "albums": (Album, "title")}.get(parts[0], (None, ""))
    if model is None:
        return ""
    with SessionLocal() as db:
        row = db.get(model, int(parts[1]))
        return str(getattr(row, attr) or "") if row else ""


def _changes(body: bytes) -> str:
    import json  # noqa: PLC0415

    try:
        data = json.loads(body) if body else None
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    out = []
    for key, value in data.items():
        if value is None:
            continue
        out.append(f"{key}={value}" if key in SHOWN and not isinstance(value, (dict, list)) else key)
    return ", ".join(out)


class AdminChanges:
    """ASGI middleware: other requests (streams too) pass straight through, untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE")
                or not scope["path"].startswith(ADMIN_PREFIX) or scope["path"].endswith("/preview")):
            return await self.app(scope, receive, send)
        from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

        from .security import COOKIE_NAME, session_user  # noqa: PLC0415

        # read the body (small JSON), then hand it on as it came
        chunks, more = [], True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            more = message.get("more_body", False)
        body = b"".join(chunks)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        status = 500

        async def watch(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        request = Request(scope)

        def who() -> tuple[User | None, str]:
            token = request.cookies.get(COOKIE_NAME)
            with SessionLocal() as db:
                user = session_user(db, token) if token else None
                if user is not None:
                    db.expunge(user)
            return user, _target(scope["path"])

        user, target = await run_in_threadpool(who)
        await self.app(scope, replay, watch)
        if user is not None and user.is_admin and status < 400:
            route = getattr(scope.get("route"), "path", "") or scope["path"]
            detail = " | ".join(x for x in (f"{scope['method']} {route.removeprefix('/api/v1')}", target, _changes(body)) if x)
            await run_in_threadpool(record, "admin", user, detail=detail, request=request)
