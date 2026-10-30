"""Brings the database up to this image's schema at startup (run by entrypoint.sh).

All pending migrations run in one transaction (PostgreSQL DDL is transactional): if one fails,
the database stays exactly as it was and the old image still works with it.
A database newer than this image (going back to an older image after an update) is refused
with a clear message instead of a crash loop with an alembic traceback.
"""

import logging
import sys
import time
import traceback
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from .config import settings

log = logging.getLogger("migrate")

WAIT_SECONDS = 120


def current_revision(engine) -> str | None:
    """Waits for the database: on the very first start PostgreSQL initializes, restarts once,
    and on a slow NAS can still be starting when the app comes up."""
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        try:
            with engine.connect() as conn:
                return MigrationContext.configure(conn).get_current_revision()
        except OperationalError as exc:
            if time.monotonic() > deadline:
                raise
            log.info("waiting for the database (%s)", str(exc.orig).strip().splitlines()[0][:120])
            time.sleep(3)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    engine = create_engine(settings.database_url)
    current = current_revision(engine)
    engine.dispose()

    if current == head:
        log.info("database schema is up to date (%s)", head)
        return 0
    try:
        if current is not None:
            script.get_revision(current)
    except CommandError:
        log.error(
            "The database (schema %s) is newer than this image (schema %s), so it was not changed. "
            "Use the newer image again, or restore the backup taken before the update.",
            current,
            head,
        )
        return 1
    log.info("migrating database schema %s -> %s", current or "(empty)", head)
    try:
        command.upgrade(cfg, "head")
    except Exception:
        # alembic's env.py reconfigures logging (and silences this logger), so write directly
        traceback.print_exc()
        print("ERROR migrate: migration failed; the database was rolled back and left unchanged", file=sys.stderr)
        return 1
    print("INFO migrate: migration done", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
