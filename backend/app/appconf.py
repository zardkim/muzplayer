"""Settings an admin changes in the app (AI banner and YouTube keys), kept in CONF_DIR/settings.json.

The file is readable by the app user only. Keys are never sent back to the browser or logged:
the admin page only learns whether each one is set.
"""

import json
import logging
import os
import threading

from .config import settings

log = logging.getLogger(__name__)

DEFAULTS = {
    "ai_provider": "gemini",
    "gemini_api_key": "",
    "gemini_image_model": "",  # empty = DEFAULT_MODELS
    "openai_api_key": "",
    "openai_image_model": "",
    "gemini_text_model": "",  # AI playlists; empty = DEFAULT_TEXT_MODELS
    "openai_text_model": "",
    "youtube_api_key": "",
}
SECRETS = ("gemini_api_key", "openai_api_key", "youtube_api_key")
DEFAULT_MODELS = {"gemini": "gemini-nano-banana-2.1", "openai": "gpt-image-2.5-flare"}
DEFAULT_TEXT_MODELS = {"gemini": "gemini-3.8-flash", "openai": "gpt-6-astra"}

_lock = threading.Lock()
_cache: dict | None = None


def _file():
    return settings.conf_dir / "settings.json"


def _load() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            data = {}
            try:
                data = json.loads(_file().read_text(encoding="utf-8"))
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as exc:
                log.warning("could not read %s: %s", _file(), type(exc).__name__)
            _cache = {k: str(data.get(k) or v).strip() for k, v in DEFAULTS.items()}
        return _cache


def get(key: str) -> str:
    return _load()[key]


def update(changes: dict[str, str]) -> None:
    """Writes the given values (empty string clears one) and keeps the rest."""
    global _cache
    data = {**_load(), **{k: v.strip() for k, v in changes.items() if k in DEFAULTS}}
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in data.items() if v != DEFAULTS[k]}, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    with _lock:
        _cache = data


def provider() -> str:
    return "openai" if get("ai_provider") == "openai" else "gemini"


def image_model(which: str | None = None) -> str:
    which = which or provider()
    return get(f"{which}_image_model") or DEFAULT_MODELS[which]


def text_model(which: str | None = None) -> str:
    which = which or provider()
    return get(f"{which}_text_model") or DEFAULT_TEXT_MODELS[which]
