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
    # music videos on the NAS (library/video): registered one by one on the Music videos page
    video_dir: Path = Path(os.getenv("VIDEO_DIR", "/library/video"))
    # audio taken out of music videos (extract.py): a folder of the music library mounted writable
    # (the rest of the library stays read-only); scanned as the "extracted" kind
    extract_dir: Path = Path(os.getenv("EXTRACT_DIR", "") or Path(os.getenv("MUSIC_DIR", "/library/music")) / "cover music")
    # JavaScript runtime yt-dlp needs for YouTube (the image has one)
    deno_path: str = os.getenv("DENO_PATH", "").strip() or "deno"
    data_dir: Path = Path(os.getenv("DATA_DIR", "/data"))
    # settings changed in the app (API keys): conf/settings.json
    conf_dir: Path = Path(os.getenv("CONF_DIR", "/conf"))
    static_dir: Path = Path(os.getenv("STATIC_DIR", "/app/static"))
    cookie_secure: bool = _bool("COOKIE_SECURE", True)
    session_days: int = int(os.getenv("SESSION_DAYS", "60"))
    scan_interval_minutes: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "60"))  # 0 = manual only
    default_locale: str = os.getenv("DEFAULT_LOCALE", "ko")
    # converting songs (quality, WMA/APE, levelling on the server): the image has its own ffmpeg
    ffmpeg_path: str = os.getenv("FFMPEG_PATH", "").strip() or "ffmpeg"
    transcode_cache_mb: int = int(os.getenv("TRANSCODE_CACHE_MB", "2048"))
    version: str = os.getenv("APP_VERSION", "dev")
    # the Windows app's releases (a public Gitea repository): Settings → add to home screen offers its installer
    windows_app_releases: str = os.getenv(
        "WINDOWS_APP_RELEASES", "https://gitea.nurilab.pe.kr/nuricom/muzplayer-windows/releases"
    ).rstrip("/")

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
