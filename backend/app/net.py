"""Requests to other sites (Bugs, Melon, LRCLIB, Wikipedia, the broadcasters): one browser
User-Agent for the sites that turn away bots, one descriptive one for the open APIs that ask for it."""

import json
import urllib.request

from bs4 import BeautifulSoup

from .config import settings

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# Wikimedia and MusicBrainz: who is asking and where to reach them
APP_UA = f"muzplayer/{settings.version} (self-hosted music player; https://github.com/zardkim/muzplayer)"
TIMEOUT = 15
ACCEPT_LANGUAGE = "ko-KR,ko;q=0.9,en-US;q=0.8"


def open_url(url: str, *, headers: dict | None = None, data: bytes | None = None, timeout: float = TIMEOUT):
    """The response, still open (close it, or use it in a with). The browser User-Agent unless
    headers name another."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": BROWSER_UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - callers' fixed hosts


def get(url: str, *, headers: dict | None = None, data: bytes | None = None, timeout: float = TIMEOUT, limit: int | None = None) -> bytes:
    """The body (at most limit bytes)."""
    with open_url(url, headers=headers, data=data, timeout=timeout) as resp:
        return resp.read(limit)


def get_json(url: str, *, headers: dict | None = None, timeout: float = TIMEOUT):
    return json.loads(get(url, headers={"Accept": "application/json", **(headers or {})}, timeout=timeout))


def get_page(url: str, referer: str, *, timeout: float = TIMEOUT) -> BeautifulSoup:
    """A web page as a browser opening it from referer would get it."""
    data = get(url, timeout=timeout, headers={
        "Referer": referer, "Accept-Language": ACCEPT_LANGUAGE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser")
