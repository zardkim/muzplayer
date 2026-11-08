import logging
import mimetypes
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import activity, search_index
from .api import admin, auth, books, collections, library, marks, me, mixes, news, radio, stations, videos
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
    search_index.rebuild_in_background()  # only when an update changed how the index is built
    yield
    stop.set()


app = FastAPI(title="muzplayer", version=settings.version, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(activity.AdminChanges)  # the admin's log page

API = "/api/v1"
for module in (auth, library, collections, me, marks, mixes, stations, videos, admin, books, radio, news):
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

    # The home screen icon picked in Settings (cookie muz_icon, set by the app): written into the page
    # itself. iPhone takes the icon when the page is added to the home screen, from the links the page
    # came with (one changed by a script afterwards may be missed).
    APP_ICONS = ("light", "dark", "pink", "navy")

    def index_html(icon: str | None) -> Response:
        html = index_file.read_text(encoding="utf-8")
        if icon in APP_ICONS and icon != "light":
            html = html.replace('href="/icon-1', f'href="/icon-{icon}-1').replace(
                'href="/manifest.webmanifest"', f'href="/manifest-{icon}.webmanifest"'
            )
        return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache", "Vary": "Cookie"})

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request):
        candidate = (settings.static_dir / path).resolve()
        if path and path != "index.html" and candidate.is_file() and candidate.is_relative_to(settings.static_dir.resolve()):
            no_cache = path in ("sw.js",) or path.endswith(".webmanifest")
            return FileResponse(candidate, headers={"Cache-Control": "no-cache"} if no_cache else None)
        return index_html(request.cookies.get("muz_icon"))
