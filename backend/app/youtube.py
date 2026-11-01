"""YouTube for album/song videos: search (Data API, needs the key an admin sets in the app) and checking a picked
or pasted video (oEmbed, no key). The key goes in a header, never in a URL or the logs."""

import html
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from . import appconf

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
OEMBED_URL = "https://www.youtube.com/oembed"
TIMEOUT = 15
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
# watch?v=, youtu.be/, shorts/, embed/, live/, music.youtube.com
URL_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")


class YoutubeError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def configured() -> bool:
    return bool(appconf.get("youtube_api_key"))


def video_id(text: str) -> str | None:
    """The 11-character id from a YouTube link (or the id itself)."""
    text = text.strip()
    if VIDEO_ID.match(text):
        return text
    m = URL_ID.search(text)
    return m.group(1) if m else None


def _get(url: str, params: dict, key: bool) -> dict:
    headers = {"Accept": "application/json"}
    if key:
        headers["x-goog-api-key"] = appconf.get("youtube_api_key")
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:  # noqa: S310 - fixed API hosts
            return json.loads(res.read())
    except urllib.error.HTTPError as exc:
        if url == OEMBED_URL:
            # 400/404: no such video (or private); 401/403: its owner turned embedding off
            raise YoutubeError("video_not_embeddable" if exc.code in (401, 403) else "video_not_found") from None
        log.warning("youtube search: %s %s", exc.code, exc.read(400).decode("utf-8", "replace"))
        if exc.code == 403:
            raise YoutubeError("youtube_quota") from None  # also a key without the Data API enabled
        if exc.code in (400, 401):
            raise YoutubeError("youtube_unauthorized") from None
        raise YoutubeError("youtube_unreachable") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise YoutubeError("youtube_unreachable") from None


def _seconds(iso: str) -> int | None:
    """PT4M13S -> 253."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def search(q: str) -> list[dict]:
    """Up to 50 videos (the most one call gives) that can be played on other sites. Costs 101 of the
    10,000 daily units, whatever the number."""
    if not configured():
        raise YoutubeError("youtube_not_configured")
    data = _get(
        SEARCH_URL,
        {"part": "snippet", "type": "video", "videoEmbeddable": "true", "maxResults": 50, "q": q, "regionCode": "KR"},
        key=True,
    )
    items = [i for i in data.get("items", []) if i.get("id", {}).get("videoId")]
    ids = [i["id"]["videoId"] for i in items]
    durations: dict[str, int | None] = {}
    if ids:
        details = _get(VIDEOS_URL, {"part": "contentDetails", "id": ",".join(ids)}, key=True)
        durations = {d["id"]: _seconds(d.get("contentDetails", {}).get("duration", "")) for d in details.get("items", [])}
    out = []
    for item in items:
        snippet = item.get("snippet", {})
        vid = item["id"]["videoId"]
        out.append(
            {
                "youtube_id": vid,
                "title": html.unescape(snippet.get("title", "")),  # the API escapes &, ' and "
                "channel": html.unescape(snippet.get("channelTitle", "")),
                "published_at": snippet.get("publishedAt"),
                "duration": durations.get(vid),
            }
        )
    return out


def check(youtube_id: str) -> dict:
    """Title and channel of one video, which must exist and allow embedding."""
    data = _get(OEMBED_URL, {"url": f"https://www.youtube.com/watch?v={youtube_id}", "format": "json"}, key=False)
    return {"title": str(data.get("title", ""))[:500], "channel": str(data.get("author_name", ""))[:200]}
