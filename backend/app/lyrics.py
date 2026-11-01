"""Lyrics read on demand from the music file or a .lrc file next to it. Never written."""

import re
from pathlib import Path

import mutagen

# [mm:ss], [mm:ss.xx], [mm:ss:xx], [mm:ss,xx]; a line may carry several stamps (repeated chorus)
STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:,](\d{1,3}))?\]")
WORD_STAMP = re.compile(r"<\d{1,3}:\d{1,2}(?:[.:,]\d{1,3})?>")  # enhanced LRC: per-word times
OFFSET = re.compile(r"^\[offset:\s*([+-]?\d+)\]", re.IGNORECASE | re.MULTILINE)
META = re.compile(r"^\[[a-z]+:.*\]\s*$", re.IGNORECASE)  # [ar:..] [ti:..] [by:..]
INVISIBLE = dict.fromkeys(map(ord, "\ufeff\u200b\u200c\u200d\u2060"))  # BOM and zero-width marks
TAG_KEYS = {"lyrics", "unsyncedlyrics", "unsynced lyrics", "syncedlyrics", "wm/lyrics", "©lyr"}


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
    """Song.lrc next to Song.mp3 (any case: .LRC, .Lrc)."""
    want = (path.stem + ".lrc").casefold()
    try:
        for entry in path.parent.iterdir():
            if entry.name.casefold() == want and entry.is_file():
                return _decode(entry.read_bytes()[:512_000])
    except OSError:
        pass
    return None


def _from_tags(path: Path) -> list[str]:
    """Every lyrics text in the tags. A file may hold plain lyrics and an LRC side by side
    (two USLT frames, or USLT plus TXXX:LYRICS from Mp3tag/foobar), so all of them are kept."""
    audio = mutagen.File(path)
    tags = getattr(audio, "tags", None)
    if not tags:
        return []
    found: list[str] = []
    if hasattr(tags, "getall"):  # ID3
        found += [str(f.text) for f in tags.getall("USLT")]
        for frame in tags.getall("SYLT"):
            if frame.format == 2 and frame.text:  # milliseconds
                found.append("\n".join(
                    f"[{ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms % 1000 // 10:02d}]{text.strip()}"
                    for text, ms in frame.text
                ))
        for frame in tags.getall("TXXX"):
            if str(frame.desc).strip().lower() in TAG_KEYS:
                found += [str(t) for t in frame.text]
    else:
        for key in tags.keys():
            if str(key).lower() in TAG_KEYS:
                values = tags[key]
                for value in values if isinstance(values, list) else [values]:
                    text = getattr(value, "value", value)  # ASF attributes wrap the text
                    if not isinstance(text, bytes):
                        found.append(str(text))
    return [t for t in found if t.strip()]


def synced_in_tags(path: Path) -> bool:
    """Whether the tags hold synced lyrics (LRC); the scanner keeps the answer (tracks.lrc_tag)."""
    try:
        return any(parse(t)["synced"] for t in _from_tags(path))
    except Exception:  # unreadable tags: no lyrics
        return False


def parse(text: str) -> dict:
    """Returns {"synced": [[seconds, line], ...] | None, "plain": str | None}."""
    text = text.translate(INVISIBLE).replace("\r\n", "\n").replace("\r", "\n").strip()
    offset = OFFSET.search(text)
    shift = int(offset.group(1)) / 1000 if offset else 0.0  # positive offset shows lines earlier
    synced: list[list] = []
    plain: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        stamps = list(STAMP.finditer(line))
        if stamps and stamps[0].start() == 0:
            words = WORD_STAMP.sub("", STAMP.sub("", line)).strip()
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
    """The first synced (LRC) lyrics found, .lrc next to the file first, then the tags;
    plain lyrics only when nothing is synced."""
    texts = []
    sidecar = _sidecar(path)
    if sidecar:
        texts.append(sidecar)
    try:
        texts += _from_tags(path)
    except Exception:
        pass
    plain = None
    for text in texts:
        result = parse(text)
        if result["synced"]:
            return result
        plain = plain or result["plain"]
    return {"synced": None, "plain": plain}
