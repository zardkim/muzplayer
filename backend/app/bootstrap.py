"""Run once at container start (after migrations): creates the first admin when there are no users."""

import logging

from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal
from .models import User
from .security import hash_password

log = logging.getLogger("bootstrap")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return
        if not settings.admin_username or len(settings.admin_password) < 8:
            log.warning("No users exist. Set ADMIN_USERNAME and ADMIN_PASSWORD (8+ chars) in .env and restart.")
            return
        db.add(
            User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                display_name=settings.admin_username,
                is_admin=True,
            )
        )
        db.commit()
        log.info("Created admin user '%s'. You can now remove ADMIN_PASSWORD from .env.", settings.admin_username)


if __name__ == "__main__":
    main()
