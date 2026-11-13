"""Admins fix a song's lyrics: wrong ones shown, or out of time. Lyrics to choose from are looked
up on AlSong (the file itself, then by name), Bugs and LRCLIB (lyrics_fetch.candidates); the one
chosen (or written; its timing shifted when asked) is written as an .lrc file in DATA_DIR/lrc, at
the song's own path (app/lrc/<album folder>/<song>.lrc: other players and taggers can use it), and
shown ahead of the song's own .lrc or tags. A copy stays in the database (fetched_lyrics, pinned:
the lists' lyrics marks, backups); "none" is kept there alone. The library stays read-only.
"""

import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import lyrics_fetch
from ..config import settings
from ..db import get_db
from ..library_paths import chosen_lrc
from ..lyrics import own_texts, parse, read_text, shift_lrc
from ..models import Album, FetchedLyrics, User
from ..security import admin_user, api_error
from .library import track_file

router = APIRouter()
SOURCES = ("alsong", "bugs", "lrclib")


@router.get("/admin/lyrics/{track_id}")
def get_lyrics(track_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """The song, its own lyrics (as written), what was looked up or chosen for it, and which is shown."""
    track, path = track_file(db, track_id)
    own = own_texts(Path(path))
    row = db.get(FetchedLyrics, track.id)
    album = db.scalar(select(Album.title).where(Album.id == track.album_id)) if track.album_id else ""
    own_synced = next((t for t in own if parse(t)["synced"]), None)
    lrc = chosen_lrc(track.file_path)
    chosen = (read_text(lrc) if lrc and lrc.is_file() else None) or (row.lrc if row else None)
    if row is not None and row.pinned:
        shown = "pinned" if row.lrc else "hidden"
    elif own_synced or (own and not (row and row.lrc and parse(row.lrc)["synced"])):
        shown = "own"
    else:
        shown = "fetched" if row and row.lrc else "none"
    return {
        "track": {"id": track.id, "title": track.title, "artist": track.artist_text, "album": album or "", "duration": track.duration},
        "own": own_synced or (own[0] if own else None),
        "saved": {"lrc": chosen if row.pinned else row.lrc, "source": row.source, "pinned": row.pinned} if row else None,
        "file": lrc.relative_to(settings.data_dir).as_posix() if lrc and row is not None and row.pinned and lrc.is_file() else None,  # under app/
        "shown": shown,
    }


class SearchIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field("", max_length=300)
    sources: list[Literal["alsong", "bugs", "lrclib"]] = list(SOURCES)


@router.post("/admin/lyrics/{track_id}/search")
async def search_lyrics(track_id: int, body: SearchIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    _, path = track_file(db, track_id)
    db.close()  # the sites take seconds: no pool connection held meanwhile
    return await run_in_threadpool(lyrics_fetch.candidates, body.title.strip(), body.artist.strip(), Path(path), body.sources)


class LyricsIn(BaseModel):
    lrc: str | None = Field(None, max_length=200_000)  # None: no lyrics shown for this song
    source: Literal["alsong", "bugs", "lrclib", "manual", "own"] = "manual"
    offset_ms: int = Field(0, ge=-60_000, le=60_000)  # moves every line (+ later), written into the file


def _write(path: Path, text: str) -> None:
    """The .lrc, whole (a temporary file renamed over it), UTF-8 as players expect."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".lrc-")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    os.replace(tmp, path)


def _remove(path: Path | None) -> None:
    """The song's .lrc in DATA_DIR/lrc, and its folders left empty."""
    if path is None:
        return
    path.unlink(missing_ok=True)
    base = settings.data_dir / "lrc"
    for parent in path.parents:
        if parent == base or base not in parent.parents:
            break
        try:
            parent.rmdir()  # only when empty
        except OSError:
            break


@router.put("/admin/lyrics/{track_id}")
def put_lyrics(track_id: int, body: LyricsIn, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Keeps these lyrics for the song (or none), ahead of its own: as its .lrc in DATA_DIR/lrc."""
    track, _path = track_file(db, track_id)
    text = (body.lrc or "").strip() or None
    if text is not None:
        if not (parse(text)["synced"] or parse(text)["plain"]):
            raise api_error(400, "lyrics_empty")
        text = shift_lrc(text, body.offset_ms)
    path = chosen_lrc(track.file_path)
    if path is None:
        raise api_error(400, "invalid_folder")
    if text is None:
        _remove(path)
    else:
        _write(path, text)
    row = db.get(FetchedLyrics, track.id) or FetchedLyrics(track_id=track.id)
    row.lrc, row.source, row.pinned = text, body.source if text else None, True
    db.merge(row)
    db.commit()
    return {"ok": True, "file": path.relative_to(settings.data_dir).as_posix() if text else None}


@router.delete("/admin/lyrics/{track_id}", status_code=204)
def reset_lyrics(track_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db, scope="function")):
    """Back to the song's own lyrics, or looked up again by themselves (its .lrc in DATA_DIR/lrc goes)."""
    track, _path = track_file(db, track_id)
    _remove(chosen_lrc(track.file_path))
    row = db.get(FetchedLyrics, track.id)
    if row is not None:
        db.delete(row)
        db.commit()
