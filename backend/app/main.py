import logging
import mimetypes
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, auth, books, cast, collections, library, marks, me, mixes, remote, videos
from .config import settings
from .db import SessionLocal
from .scanner import mark_interrupted_jobs, start_auto_scan

mimetypes.add_type("application/manifest+json", ".webmanifest")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        mark_interrupted_jobs(db)
    stop = threading.Event()
    start_auto_scan(stop)
    yield
    stop.set()


app = FastAPI(title="muzplayer", version=settings.version, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

API = "/api/v1"
for module in (auth, library, collections, me, marks, mixes, videos, admin, books, remote, cast):
    app.include_router(module.router, prefix=API)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def api_not_found(rest: str):
    raise HTTPException(status_code=404, detail="not_found")


# Built Vue app. Unknown paths fall back to index.html for client-side routing.
index_file = settings.static_dir / "index.html"
if index_file.exists():
    app.mount("/assets", StaticFiles(directory=settings.static_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (settings.static_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(settings.static_dir.resolve()):
            no_cache = path in ("sw.js", "manifest.webmanifest")
            return FileResponse(candidate, headers={"Cache-Control": "no-cache"} if no_cache else None)
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})
