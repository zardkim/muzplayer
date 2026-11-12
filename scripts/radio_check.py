"""Checks that every radio station plays: resolves its stream the way the server does (radio.resolve)
and reads the start of it (an HLS playlist with segments, or audio). Run from backend/:

    ../.venv/bin/python ../scripts/radio_check.py [station id ...]

Prints one line a station and the ones that failed at the end; exit status 1 when any did.
"""

import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")
from app import radio  # noqa: E402


def check(station: dict) -> tuple[str, str]:
    try:
        url, ctype = radio.resolve(station)
        if radio._is_hls(url, ctype):
            base, text = radio._playlist(url)
            if "#EXT-X-STREAM-INF" in text:  # variants: the first
                base, text = radio._playlist(urllib.parse.urljoin(base, next(l for l in text.splitlines() if l and not l.startswith("#"))))
            segments = [l for l in text.splitlines() if l and not l.startswith("#")]
            if not segments:
                return "FAIL", "playlist without segments"
            with radio._open(urllib.parse.urljoin(base, segments[-1])) as resp:
                return ("ok", f"hls {len(resp.read(65536))}B") if resp.status == 200 else ("FAIL", f"segment {resp.status}")
        with radio._open(url) as resp:
            n = len(resp.read(32768))
            return ("ok", f"{ctype or '?'} {n}B") if n else ("FAIL", "no audio")
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"{type(exc).__name__}: {str(exc)[:80]}"


def main() -> int:
    want = set(sys.argv[1:])
    stations = [s for s in radio.STATIONS if not want or s["id"] in want]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(check, stations))
    failed = []
    for s, (status, detail) in zip(stations, results):
        print(f"{status:4} {s['id']:28} {detail}")
        if status != "ok":
            failed.append(s["id"])
    print(f"\n{len(stations) - len(failed)}/{len(stations)} play" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
