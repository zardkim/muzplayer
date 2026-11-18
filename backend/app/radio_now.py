"""What a station has on air now (the Radio page's tuner, docs/radio_tuner_plan.md 2.3): the
programme's title and hours, from the broadcaster's own schedule (checked 2026-11-12):

  - KBS: static.api.kbs.co.kr onair_now, by channel (21 1R, 22 2R, 23 3R, 24 1FM, 25 2FM, 26 한민족)
  - SBS: apis.sbs.co.kr onair, by channel (S07 파워FM, S08 러브FM, S19 고릴라디오M)
  - MBC: miniunit.imbc.com Schedule, the week's programmes by channel (STFM, FM4U, CHAM): the one
    started last today (or the last of yesterday's, after midnight)
  - EBS: www.ebs.co.kr cururentOnair, by channel (RADIO FM, IRADIO 반디); the same in every region

Seoul's stations only for KBS, SBS and MBC: the regional ones have programmes of their own at times.
Kept a minute (MBC's week an hour); a broadcaster not answering is "nothing known", never an error.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import net

log = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
TIMEOUT = 6
KEPT = 60
SOURCES: dict[str, tuple[str, str]] = {
    "kbs-1radio": ("kbs", "21"), "kbs-2radio": ("kbs", "22"), "kbs-3radio": ("kbs", "23"),
    "kbs-1fm": ("kbs", "24"), "kbs-2fm": ("kbs", "25"), "kbs-hanminjok": ("kbs", "26"),
    "sbs-powerfm": ("sbs", "S07"), "sbs-lovefm": ("sbs", "S08"), "sbs-dmb": ("sbs", "S19"),
    "mbc-sfm": ("mbc", "STFM"), "mbc-fm4u": ("mbc", "FM4U"), "mbc-chm": ("mbc", "CHAM"),
    "ebs-fm": ("ebs", "RADIO"), "ebs-bandi": ("ebs", "IRADIO"),
}
_cache: dict[str, tuple[float, dict | None]] = {}
_lock = threading.Lock()


def _json(url: str):
    return net.get_json(url, timeout=TIMEOUT)


def _hhmm(text: str | None) -> str | None:
    """"22000000" / "2200" / "22:00" -> "22:00"."""
    digits = "".join(c for c in text or "" if c.isdigit())
    return f"{digits[:2]}:{digits[2:4]}" if len(digits) >= 4 else None


def _kbs(channel: str) -> dict | None:
    data = _json(f"https://static.api.kbs.co.kr/mediafactory/v1/schedule/onair_now?rtype=json&local_station_code=00&channel_code={channel}")
    s = (data[0].get("schedules") or [None])[0] if data else None
    if not s or not s.get("program_title"):
        return None
    return {"title": s["program_title"], "start": _hhmm(s.get("service_start_time")), "end": _hhmm(s.get("service_end_time"))}


def _sbs(channel: str) -> dict | None:
    info = _json(f"https://apis.sbs.co.kr/play-api/1.0/onair/channel/{channel}?v_type=2&platform=pcweb&protocol=hls&jwt-token=&ssl=Y")["onair"]["info"]
    return {"title": info["title"], "start": None, "end": None} if info.get("title") else None


_DAYS = "월화수목금토일"


def _mbc(channel: str) -> dict | None:
    week = _cached("mbc:week", 3600, lambda: _json("https://miniunit.imbc.com/Schedule?rtype=json")["Programs"])
    if not week:
        return None
    now = datetime.now(KST)
    hm = now.strftime("%H%M")
    today, yesterday = _DAYS[now.weekday()], _DAYS[(now - timedelta(days=1)).weekday()]
    mine = [p for p in week if p.get("Channel") == channel and p.get("StartTime")]
    day = sorted((p for p in mine if p.get("LiveDays") == today), key=lambda p: p["StartTime"])
    started = [p for p in day if p["StartTime"] <= hm]
    cur = started[-1] if started else max((p for p in mine if p.get("LiveDays") == yesterday), key=lambda p: p["StartTime"], default=None)
    if cur is None:
        return None
    later = [p for p in day if p["StartTime"] > hm]
    return {"title": cur["ProgramTitle"], "start": _hhmm(cur["StartTime"]), "end": _hhmm(later[0]["StartTime"]) if later else None}


def _ebs(channel: str) -> dict | None:
    p = _json(f"https://www.ebs.co.kr/onair/cururentOnair.json?channelCd={channel}").get("nowProgram") or {}
    return {"title": p["title"], "start": _hhmm(p.get("start")), "end": _hhmm(p.get("end"))} if p.get("title") else None


_FETCH = {"kbs": _kbs, "sbs": _sbs, "mbc": _mbc, "ebs": _ebs}


def _cached(key: str, ttl: float, fetch):
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
    try:
        value = fetch()
    except Exception as exc:  # noqa: BLE001 - the broadcaster moved or blocked it: nothing known
        log.info("radio now %s: %s", key, exc)
        value = None
    with _lock:
        _cache[key] = (time.monotonic(), value)
    return value


def now(station_id: str) -> dict | None:
    """{"title", "start", "end"} of what the station has on air now (start/end "HH:MM" or None), or None."""
    src = SOURCES.get(station_id)
    if not src:
        return None
    kind, channel = src
    return _cached(f"{kind}:{channel}", KEPT, lambda: _FETCH[kind](channel))
