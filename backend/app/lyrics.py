"""Lyrics read on demand from the music file or a .lrc file next to it. Never written."""

import re
from pathlib import Path

import mutagen

# [mm:ss], [mm:ss.xx], [mm:ss:xx]; a line may carry several stamps (repeated chorus)
STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
OFFSET = re.compile(r"^\[offset:\s*([+-]?\d+)\]", re.IGNORECASE | re.MULTILINE)
META = re.compile(r"^\[[a-z]+:.*\]\s*$", re.IGNORECASE)  # [ar:..] [ti:..] [by:..]
TAG_KEYS = {"lyrics", "unsyncedlyrics", "unsynced lyrics", "wm/lyrics", "©lyr"}


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    # .lrc files made with Korean Windows tools are often CP949
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _sidecar(path: Path) -> str | None:
    for candidate in (path.with_suffix(".lrc"), path.with_suffix(".LRC")):
        if candidate.is_file():
            return _decode(candidate.read_bytes()[:512_000])
    return None


def _from_tags(path: Path) -> str | None:
    audio = mutagen.File(path)
    tags = getattr(audio, "tags", None)
    if not tags:
        return None
    if hasattr(tags, "getall"):  # ID3
        for frame in tags.getall("USLT"):
            if str(frame.text).strip():
                return str(frame.text)
        for frame in tags.getall("SYLT"):
            if frame.format == 2 and frame.text:  # milliseconds
                return "\n".join(
                    f"[{ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms % 1000 // 10:02d}]{text.strip()}"
                    for text, ms in frame.text
                )
        return None
    for key in tags.keys():
        if str(key).lower() in TAG_KEYS:
            values = tags[key]
            for value in values if isinstance(values, list) else [values]:
                text = getattr(value, "value", value)  # ASF attributes wrap the text
                if not isinstance(text, bytes) and str(text).strip():
                    return str(text)
    return None


def parse(text: str) -> dict:
    """Returns {"synced": [[seconds, line], ...] | None, "plain": str | None}."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    offset = OFFSET.search(text)
    shift = int(offset.group(1)) / 1000 if offset else 0.0  # positive offset shows lines earlier
    synced: list[list] = []
    plain: list[str] = []
    for line in text.split("\n"):
        stamps = list(STAMP.finditer(line))
        if stamps and stamps[0].start() == 0:
            words = STAMP.sub("", line).strip()
            for m in stamps:
                frac = m.group(3) or "0"
                seconds = int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / (10 ** len(frac))
                synced.append([round(max(0.0, seconds - shift), 2), words])
            plain.append(words)
        elif not META.match(line):
            plain.append(line.strip())
    if len(synced) >= 2:
        synced.sort(key=lambda x: x[0])
        return {"synced": synced, "plain": "\n".join(plain).strip() or None}
    body = "\n".join(plain).strip()
    return {"synced": None, "plain": body or None}


def read_lyrics(path: Path) -> dict:
    """.lrc next to the file wins (usually synced), then embedded tags."""
    text = _sidecar(path)
    if text is None:
        try:
            text = _from_tags(path)
        except Exception:
            text = None
    if not text or not text.strip():
        return {"synced": None, "plain": None}
    return parse(text)
