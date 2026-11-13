"""Backup and restore (Admin → Backup): the settings (CONF_DIR) and the database, never the library's
files, covers or photos (DATA_DIR: on another NAS the covers are made again by a scan started after
the restore, and artist photos looked up again).

A backup is a .tar.gz kept in DATA_DIR/backups (the last KEEP), made of
  manifest.json   format, app version, schema revision, and each table's columns and row count
  db/<table>.copy each table as PostgreSQL's COPY text (the sessions table left out: login tokens)
  conf/<file>     the settings files (settings.json holds API keys: the backup is as secret)

Restoring checks the whole file first, then in one transaction on one connection: drops every
table, builds the schema of the backup's revision (alembic, as a first start does), loads the
tables, sets the id sequences past the loaded rows, and migrates to this image's schema (as an
update does). Anything failing leaves the database as it was. Everyone signs in again afterwards.
A backup from a newer version (a revision this image doesn't know) is refused.
"""

import io
import json
import logging
import os
import re
import shutil
import tarfile
import tempfile
import threading
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import text

from . import appconf, cache
from .config import settings
from .db import Base, engine

log = logging.getLogger(__name__)

FORMAT = 1
KEEP = 5
LEFT_OUT = {"sessions"}  # login tokens: not in a file, and a restore signs everyone out anyway
NAME = re.compile(r"^muzplayer-[\w.-]+\.tar\.gz$")
_running = threading.Lock()  # one backup or restore at a time


class BackupError(Exception):
    """Carries only a code for the frontend."""


def folder() -> Path:
    return settings.data_dir / "backups"


def _alembic() -> Config:
    return Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))


def listing() -> list[dict]:
    """The backups kept, newest first."""
    if not folder().is_dir():
        return []
    out = []
    for p in folder().iterdir():
        if NAME.match(p.name) and p.is_file():
            st = p.stat()
            out.append({"name": p.name, "size": st.st_size, "created": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return sorted(out, key=lambda b: b["created"], reverse=True)


def path_of(name: str) -> Path:
    p = folder() / name
    if not NAME.match(name) or not p.is_file():
        raise BackupError("not_found")
    return p


def _prune() -> None:
    for old in listing()[KEEP:]:
        (folder() / old["name"]).unlink(missing_ok=True)


def _columns(conn, table: str) -> list[str]:
    return list(conn.execute(text(
        "select column_name from information_schema.columns where table_schema = 'public' and table_name = :t order by ordinal_position"
    ), {"t": table}).scalars())


def _add(tar: tarfile.TarFile, name: str, data: bytes | Path) -> None:
    info = tarfile.TarInfo(name)
    info.mtime = int(datetime.now().timestamp())
    if isinstance(data, Path):
        info.size = data.stat().st_size
        with data.open("rb") as f:
            tar.addfile(info, f)
    else:
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


def create() -> dict:
    """Makes a backup now (a consistent snapshot of the database); returns it as listed."""
    if not _running.acquire(blocking=False):
        raise BackupError("backup_busy")
    try:
        folder().mkdir(parents=True, exist_ok=True)
        name = f"muzplayer-{settings.version}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
        tmp = folder() / f".{name}.part"
        tables = []
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn, conn.begin():
            revision = MigrationContext.configure(conn).get_current_revision()
            raw = conn.connection.driver_connection
            with tarfile.open(tmp, "w:gz", compresslevel=6) as tar, tempfile.TemporaryDirectory(dir=folder()) as work:
                for table in Base.metadata.sorted_tables:
                    cols = _columns(conn, table.name)
                    if table.name in LEFT_OUT or not cols:  # (not there: a schema older than this image's)
                        continue
                    dump = Path(work) / f"{table.name}.copy"
                    rows = 0
                    with dump.open("wb") as f, raw.cursor().copy(f'COPY "{table.name}" ({", ".join(f"{c}" for c in cols)}) TO STDOUT') as cp:
                        for chunk in cp:
                            f.write(chunk)
                            rows += bytes(chunk).count(b"\n")
                    _add(tar, f"db/{table.name}.copy", dump)
                    dump.unlink()
                    tables.append({"name": table.name, "columns": cols, "rows": rows})
                conf = []
                if settings.conf_dir.is_dir():
                    for f in sorted(settings.conf_dir.iterdir()):
                        if f.is_file() and not f.name.startswith("."):
                            _add(tar, f"conf/{f.name}", f)
                            conf.append(f.name)
                manifest = {
                    "format": FORMAT, "app": settings.version, "revision": revision,
                    "created": datetime.now().isoformat(timespec="seconds"), "tables": tables, "conf": conf,
                }
                _add(tar, "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1).encode())
        os.chmod(tmp, 0o600)  # API keys and password hashes inside
        os.replace(tmp, folder() / name)
        _prune()
        log.info("backup %s: %d tables, %d rows", name, len(tables), sum(t["rows"] for t in tables))
        return next(b for b in listing() if b["name"] == name)
    except BackupError:
        raise
    except Exception:
        log.exception("backup failed")
        for p in folder().glob(".*.part"):
            p.unlink(missing_ok=True)
        raise BackupError("backup_failed") from None
    finally:
        _running.release()


def check(path: Path) -> dict:
    """The backup's manifest, once the whole file reads right; BackupError otherwise."""
    try:
        with tarfile.open(path, "r:gz") as tar:
            members = {m.name: m for m in tar.getmembers() if m.isfile()}
            if "manifest.json" not in members:
                raise BackupError("backup_invalid")
            manifest = json.load(tar.extractfile(members["manifest.json"]))
            if manifest.get("format") != FORMAT or not isinstance(manifest.get("tables"), list):
                raise BackupError("backup_invalid")
            for t in manifest["tables"]:
                if not re.fullmatch(r"\w+", t.get("name", "")) or not all(re.fullmatch(r"\w+", c) for c in t.get("columns", [])):
                    raise BackupError("backup_invalid")
                if f"db/{t['name']}.copy" not in members:
                    raise BackupError("backup_invalid")
            for name in manifest.get("conf", []):
                if f"conf/{name}" not in members or "/" in name or name.startswith("."):
                    raise BackupError("backup_invalid")
                if name.endswith(".json"):
                    json.load(tar.extractfile(members[f"conf/{name}"]))
            # every member read to its end: a cut-off download fails here, before anything changes
            for m in members.values():
                f = tar.extractfile(m)
                while f.read(1 << 20):
                    pass
    except BackupError:
        raise
    except (tarfile.TarError, OSError, EOFError, ValueError):
        raise BackupError("backup_invalid") from None
    try:
        ScriptDirectory.from_config(_alembic()).get_revision(manifest.get("revision"))
    except CommandError:
        raise BackupError("backup_newer") from None
    if not manifest.get("revision"):
        raise BackupError("backup_invalid")
    return manifest


def _busy_locks() -> list[threading.Lock]:
    """Everything that writes the library in the background: none may run during a restore."""
    from . import album_notes, artist_aliases, artist_images, artist_links, extract, search_index
    from .scanner import scan_lock

    return [scan_lock(), artist_aliases._lock, album_notes._lookup_lock, artist_images._lock, artist_links._lock, search_index._rebuild_lock, extract._lock]


# ---- a restore runs in the background (a large library takes a while; a proxy may cut a long
# request): the admin page asks restore_status until it's done. Done, the sessions are gone too:
# that page learns it from its next question being refused (signed out), and signs in again.
status: dict = {"state": "idle"}


def start_restore(path: Path, forget_on_failure: bool = False) -> None:
    """Checks the file now (a bad one is refused at once), then restores it in the background."""
    check(path)
    if _running.locked() or status.get("state") == "running":
        raise BackupError("backup_busy")
    status.clear()
    status.update(state="running", name=path.name)

    def run() -> None:
        try:
            manifest = restore(path)
            status.update(state="done", app=manifest.get("app"), created=manifest.get("created"),
                          rows=sum(t["rows"] for t in manifest["tables"]), covers_missing=manifest.get("covers_missing", 0))
        except BackupError as exc:
            status.update(state="failed", error=str(exc))
            if forget_on_failure:
                path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            log.exception("restore failed")
            status.update(state="failed", error="restore_failed")

    threading.Thread(target=run, daemon=True, name="restore").start()


def restore(path: Path) -> dict:
    """Replaces the database and the settings with the backup's. Returns its manifest."""
    manifest = check(path)
    if not _running.acquire(blocking=False):
        raise BackupError("backup_busy")
    with ExitStack() as held:
        held.callback(_running.release)
        for lock in _busy_locks():
            if not lock.acquire(blocking=False):
                raise BackupError("backup_busy_scan")
            held.callback(lock.release)
        try:
            manifest["covers_missing"] = _load(path, manifest)
        except BackupError:
            raise
        except Exception:
            log.exception("restore failed: the database was left as it was")
            raise BackupError("restore_failed") from None
    _settings_back(path, manifest)
    # what the app keeps in memory of the old data
    appconf._cache = None
    with cache._lock:
        cache._entries.clear()
        cache._version = None
    engine.dispose()  # pooled connections with plans of the tables dropped
    if manifest["covers_missing"]:
        from .db import SessionLocal
        from .scanner import start_scan

        with SessionLocal() as db:
            start_scan(db)  # the covers missing here (scanner._refresh_covers)
    log.info("restored %s (app %s, schema %s)", path.name, manifest.get("app"), manifest.get("revision"))
    return manifest


def _load(path: Path, manifest: dict) -> int:
    """Returns how many covers the scan after it has to make again."""
    from . import artist_images
    from .books import book_cover_file
    from .scanner import cover_file

    with engine.connect() as conn, conn.begin(), tarfile.open(path, "r:gz") as tar:
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))  # an open request elsewhere: fail rather than hang
        # the library's version now: the restored one goes past it (a browser's cached lists and ETags
        # of this version must not match the restored library's)
        before = conn.execute(text("select coalesce(max(version), 0) from library_state")).scalar() if conn.execute(
            text("select to_regclass('public.library_state')")).scalar() else 0
        for (t,) in conn.execute(text("select tablename from pg_tables where schemaname = 'public'")).all():
            conn.execute(text(f'DROP TABLE IF EXISTS "{t}" CASCADE'))
        cfg = _alembic()
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, manifest["revision"])  # the schema the backup was made with
        # rows the migrations put in (library_state's one row): the backup's own instead
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t["name"]}"' for t in manifest["tables"]) + " CASCADE"))
        raw = conn.connection.driver_connection
        for t in manifest["tables"]:
            src = tar.extractfile(f"db/{t['name']}.copy")
            with raw.cursor().copy(f'COPY "{t["name"]}" ({", ".join(t["columns"])}) FROM STDIN') as cp:
                while chunk := src.read(1 << 20):
                    cp.write(chunk)
        # ids go on after the loaded rows
        for table, column in conn.execute(text(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = 'public' and column_default like 'nextval(%'"
        )).all():
            conn.execute(text(
                f"select setval(pg_get_serial_sequence('\"{table}\"', '{column}'), "
                f"coalesce((select max(\"{column}\") from \"{table}\"), 0) + 1, false)"
            ))
        command.upgrade(cfg, "head")  # then as an update would
        # covers and photos are not in a backup (another NAS, an emptied DATA_DIR): what isn't here is
        # made again by the scan that follows (covers) or looked up again (artist photos)
        missing = 0
        for (album_id,) in conn.execute(text("select id from albums where cover_path is not null")).all():
            if not cover_file(album_id, "thumb").exists():
                conn.execute(text("update albums set cover_source = null where id = :id"), {"id": album_id})
                missing += 1
        for (book_id,) in conn.execute(text("select id from books")).all():
            if not book_cover_file(book_id, "thumb").exists():
                conn.execute(text("update books set cover_sig = '!rebuild' where id = :id"), {"id": book_id})
                missing += 1
        for (artist_id,) in conn.execute(text("select id from artists where image_path is not null and image_path <> 'none'")).all():
            if not artist_images.image_file(artist_id, "thumb").exists():
                conn.execute(text("update artists set image_path = null, image_checked_at = null where id = :id"), {"id": artist_id})
        conn.execute(text("update library_state set version = greatest(version, :before) + 1"), {"before": before})
        return missing


def _settings_back(path: Path, manifest: dict) -> None:
    settings.conf_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "r:gz") as tar:
        for name in manifest.get("conf", []):
            target = settings.conf_dir / name
            tmp = target.with_name(f".{name}.restore")
            with tar.extractfile(f"conf/{name}") as src, tmp.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)
