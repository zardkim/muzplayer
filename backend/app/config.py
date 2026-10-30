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
    music_dir: Path = Path(os.getenv("MUSIC_DIR", "/music"))
    audiobook_dir: Path | None = _path("AUDIOBOOK_DIR")  # unset: audiobooks are off
    data_dir: Path = Path(os.getenv("DATA_DIR", "/data"))
    static_dir: Path = Path(os.getenv("STATIC_DIR", "/app/static"))
    cookie_secure: bool = _bool("COOKIE_SECURE", True)
    session_days: int = int(os.getenv("SESSION_DAYS", "30"))
    scan_interval_minutes: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "60"))  # 0 = manual only
    default_locale: str = os.getenv("DEFAULT_LOCALE", "ko")
    admin_username: str = os.getenv("ADMIN_USERNAME", "")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    version: str = os.getenv("APP_VERSION", "dev")
    # AI banner images for charts/themes; without a key the AI buttons are hidden
    ai_provider: str = os.getenv("AI_PROVIDER", "gemini").strip().lower() or "gemini"
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_image_model: str = os.getenv("GEMINI_IMAGE_MODEL", "").strip() or "gemini-nano-banana-2.1"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_image_model: str = os.getenv("OPENAI_IMAGE_MODEL", "").strip() or "gpt-image-2.5-flare"
    # YouTube Data API: video search when registering music videos; without it, links are pasted
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "").strip()

    @property
    def cover_dir(self) -> Path:
        return self.data_dir / "covers"


settings = Settings()

SUPPORTED_LOCALES = ("ko", "en")
