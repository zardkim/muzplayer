"""Runtime settings. Every value comes from environment variables (the deploy .env)."""

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    return Path(value) if value else None


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://muzplayer:muzplayer@localhost:5432/muzplayer"
    )
    music_dir: Path = Path(os.getenv("MUSIC_DIR", "/library/music"))
    # audiobooks are on while this folder exists and holds something (unset: always off)
    books_root: Path | None = _path("AUDIOBOOK_DIR")
    data_dir: Path = Path(os.getenv("DATA_DIR", "/data"))
    # settings changed in the app (API keys): conf/settings.json
    conf_dir: Path = Path(os.getenv("CONF_DIR", "/conf"))
    static_dir: Path = Path(os.getenv("STATIC_DIR", "/app/static"))
    cookie_secure: bool = _bool("COOKIE_SECURE", True)
    session_days: int = int(os.getenv("SESSION_DAYS", "30"))
    scan_interval_minutes: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "60"))  # 0 = manual only
    default_locale: str = os.getenv("DEFAULT_LOCALE", "ko")
    version: str = os.getenv("APP_VERSION", "dev")

    @property
    def cover_dir(self) -> Path:
        return self.data_dir / "covers"

    @property
    def audiobook_dir(self) -> Path | None:
        root = self.books_root
        if root is None:
            return None
        try:
            with os.scandir(root) as it:
                return root if any(not e.name.startswith((".", "@")) for e in it) else None
        except OSError:
            return None


settings = Settings()

SUPPORTED_LOCALES = ("ko", "en")
