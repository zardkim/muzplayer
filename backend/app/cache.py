"""Caching for large libraries: lists that are the same for every user are kept in memory until
the library changes (LibraryState.version), and answered with 304 when the browser has them.

One process (uvicorn --workers 1); the version lives in the DB so the scan thread and every
request agree on it, and so more workers would still see the same version.
"""

import hashlib
import os
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import LibraryState

MAX_ENTRIES = 500  # whole cache dropped when full; a few hundred list pages are a few MB
YEAR = "private, max-age=31536000, immutable"

_lock = threading.Lock()
_version: int | None = None
_entries: dict[str, object] = {}


def library_version(db: Session) -> int:
    return db.scalar(select(LibraryState.version)) or 0


def cached(db: Session, key: str, build: Callable[[], object]) -> tuple[int, object]:
    """(version, value) for key, building the value (JSON-ready) when this version hasn't yet."""
    global _version
    version = library_version(db)
    with _lock:
        if _version != version:
            _entries.clear()
            _version = version
        if key in _entries:
            return version, _entries[key]
    value = jsonable_encoder(build())
    with _lock:
        if _version == version:
            if len(_entries) >= MAX_ENTRIES:
                _entries.clear()
            _entries[key] = value
    return version, value


def shared_json(request: Request, db: Session, key: str, build: Callable[[], object]) -> Response:
    """A response that is the same for every user: from the cache, or 304 when unchanged.

    Never use it for anything holding per-user fields (favorites, progress).
    """
    version, value = cached(db, key, build)
    etag = f'W/"{version}-{hashlib.sha1(key.encode()).hexdigest()[:16]}"'
    # no-cache: the browser keeps it but asks each time, and gets a body-less 304 while nothing changed
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    return JSONResponse(value, headers=headers)


def image_response(request: Request, path: Path, versioned: bool) -> Response:
    """A cover file. With ?v= in the URL it never changes (a new cover gets a new version), so the
    browser keeps it for a year; without, it checks back and gets 304 while the file is the same."""
    st = os.stat(path)
    etag = f'"{int(st.st_mtime)}-{st.st_size}"'
    headers = {"ETag": etag, "Cache-Control": YEAR if versioned else "private, no-cache"}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    return FileResponse(path, media_type="image/jpeg", headers=headers, stat_result=st)
