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


def lyrics_in_tags(path: Path) -> bool:
    """Whether the tags hold lyrics, synced (LRC) or plain; the scanner keeps the answer (tracks.lrc_tag)."""
    try:
        return any(parse(t)["synced"] or parse(t)["plain"] for t in _from_tags(path))
    except Exception:  # unreadable tags: no lyrics
        return False


def _stamped(line: str, stamps: list[re.Match]) -> list[tuple[list[float], str]]:
    """A stamped line as (times, words) parts. Stamps next to each other share the words after them
    (a repeated chorus: [00:10][01:10]words); words between stamps end a part, so a whole LRC that
    lost its line breaks ([00:01]one[00:05]two..., as eztag saves AlSong lyrics) still comes apart."""
    parts: list[tuple[list[float], str]] = []
    times: list[float] = []
    for k, m in enumerate(stamps):
        frac = m.group(3) or "0"
        times.append(int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / (10 ** len(frac)))
        end = stamps[k + 1].start() if k + 1 < len(stamps) else len(line)
        words = WORD_STAMP.sub("", line[m.end():end]).strip()
        if words or k + 1 == len(stamps):
            parts.append((times, words))
            times = []
    return parts


def parse(text: str) -> dict:
    """Returns {"synced": [[seconds, line], ...] | None, "plain": str | None}."""
    text = text.translate(INVISIBLE).replace("\r\n", "\n").replace("\r", "\n").strip()
    offset = OFFSET.search(text)
    shift = int(offset.group(1)) / 1000 if offset else 0.0  # positive offset shows lines earlier
    synced: list[list] = []
    plain: list[str] = []
    last = 0.0  # the latest time so far, in the file's order
    for line in text.split("\n"):
        line = line.strip()
        stamps = list(STAMP.finditer(line))
        if stamps and stamps[0].start() == 0:
            for times, words in _stamped(line, stamps):
                # an empty line stamped earlier than the lines before it is a verse break ([00:00.00]
                # between verses, as Alsong writes them), not a pause at that time; without line
                # breaks such a break sticks to the next line's stamp ([00:00.00][00:30.00]words)
                if len(times) > 1 and any(t >= last for t in times):
                    times = [t for t in times if t >= last]
                if not words and times[0] < last:
                    continue
                last = max(last, times[0])  # (a repeated chorus's later times don't count here)
                synced += [[round(max(0.0, seconds - shift), 2), words] for seconds in times]
                plain.append(words)
        elif not META.match(line):
            plain.append(line.strip())
    if len(synced) >= 2:
        synced.sort(key=lambda x: x[0])
        # lines sharing a time are one line sung (Alsong: the original, how it is read, its
        # translation): together, one under the other, so the highlight covers all of them
        merged: list[list] = []
        for at, words in synced:
            if merged and merged[-1][0] == at:
                if words and words not in merged[-1][1].split("\n"):
                    merged[-1][1] = f"{merged[-1][1]}\n{words}" if merged[-1][1] else words
            else:
                merged.append([at, words])
        return {"synced": merged, "plain": "\n".join(plain).strip() or None}
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
