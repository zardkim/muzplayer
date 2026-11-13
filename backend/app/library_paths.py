"""Where a song's file is. Songs are kept by their path in the music library ("Album/01 Song.flac",
relative to MUSIC_DIR), and the extraction folder (extract.py) sits beside the music folder
(library/cover music, the one folder the app writes in) yet lists as a top-level folder of the
library ("cover music/<artist>/1-01 Song.m4a"). An extraction folder set inside the music folder
(EXTRACT_DIR) is simply part of it.
"""

import os
import unicodedata
from pathlib import Path

from .config import settings


def extract_top() -> str | None:
    """The extraction folder's name as a top-level library folder when it is outside the music
    folder (None when it is inside it: then it is an ordinary folder of the library)."""
    d, music = os.path.normpath(settings.extract_dir), os.path.normpath(settings.music_dir)
    if d == music or d.startswith(music + os.sep):
        return None
    return unicodedata.normalize("NFC", os.path.basename(d)) or None


def library_path(rel: str) -> Path:
    """The file (or folder) on disk for a library path."""
    top = extract_top()
    head, _, rest = rel.partition("/")
    if top is not None and unicodedata.normalize("NFC", head) == top:
        return settings.extract_dir / rest if rest else settings.extract_dir
    return settings.music_dir / rel


def library_rel(path: Path | str) -> str:
    """The library path of a file on disk (under the music folder or the extraction folder)."""
    top = extract_top()
    if top is not None:
        d = os.path.normpath(settings.extract_dir)
        p = os.path.normpath(path)
        if p == d or p.startswith(d + os.sep):
            inner = os.path.relpath(p, d)
            return top if inner == "." else f"{top}/{inner}"
    return os.path.relpath(path, settings.music_dir)


def chosen_lrc(rel: str) -> Path | None:
    """Where the lyrics an admin chose for a song are kept: DATA_DIR/lrc/<its library path>.lrc
    (the library is read-only). None for a path that would lead outside that folder."""
    base = settings.data_dir / "lrc"
    p = os.path.normpath(rel)
    if os.path.isabs(p) or p.startswith(".."):
        return None
    return base / (os.path.splitext(p)[0] + ".lrc")
