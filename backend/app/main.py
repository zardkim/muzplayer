import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, auth, library, me
from .config import settings
from .db import SessionLocal
from .scanner import mark_interrupted_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        mark_interrupted_jobs(db)
    yield


app = FastAPI(title="muzplayer", version=settings.version, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

API = "/api/v1"
for module in (auth, library, me, admin):
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
            return FileResponse(candidate)
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})
