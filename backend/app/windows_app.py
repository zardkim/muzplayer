"""The Windows app's latest installer (Settings → add to home screen, on a PC): looked up on its
public releases page's API (Gitea: <repo>/releases → /api/v1/repos/<owner>/<repo>/releases/latest),
kept for an hour. When the lookup fails the settings page links to the releases page instead."""

import json
import logging
import time
import urllib.parse
import urllib.request

from .config import settings

log = logging.getLogger(__name__)
KEEP = 3600
_cached: tuple[float, dict | None] = (0.0, None)


def _api_url(releases: str) -> str:
    """The latest release's API address: GitHub's (api.github.com) or a Gitea's (same answer fields)."""
    u = urllib.parse.urlsplit(releases)
    owner_repo = u.path.strip("/").removesuffix("/releases")
    if u.netloc.lower() in ("github.com", "www.github.com"):
        return f"https://api.github.com/repos/{owner_repo}/releases/latest"
    return urllib.parse.urlunsplit((u.scheme, u.netloc, f"/api/v1/repos/{owner_repo}/releases/latest", "", ""))


def latest() -> dict:
    global _cached
    page = settings.windows_app_releases
    at, found = _cached
    if time.monotonic() - at < KEEP and found is not None:
        return found
    out = {"page": f"{page}/latest", "version": None, "url": None, "size": None}
    try:
        with urllib.request.urlopen(_api_url(page), timeout=8) as r:
            rel = json.load(r)
        exe = next((a for a in rel.get("assets", []) if a.get("name", "").lower().endswith(".exe")), None)
        out["version"] = str(rel.get("tag_name", "")).lstrip("v") or None
        if exe:
            out["url"], out["size"] = exe.get("browser_download_url"), exe.get("size")
        _cached = (time.monotonic(), out)
    except Exception as e:  # noqa: BLE001 - offline or moved: the page link still works
        log.info("windows app lookup failed: %s", e)
        _cached = (time.monotonic() - KEEP + 300, out)  # try again in 5 minutes
    return out
