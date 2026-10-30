"""Run once at container start (after migrations): says how to make the first account."""

import logging

from sqlalchemy import func, select

from .db import SessionLocal
from .models import User

log = logging.getLogger("bootstrap")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    with SessionLocal() as db:
        if not db.scalar(select(func.count()).select_from(User)):
            log.warning("No accounts yet. Open muzplayer in a browser: the first account made there is the admin.")


if __name__ == "__main__":
    main()
