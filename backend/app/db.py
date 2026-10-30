from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """A session for one request. Always used as Depends(get_db, scope="function"): the session
    closes when the endpoint function returns, before the response is sent. With FastAPI's default
    it would stay open while a song or cover is still being sent, holding a pool connection the
    whole time; a few players plus a page of covers would use up the pool."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
