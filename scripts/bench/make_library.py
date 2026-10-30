"""Synthetic 100k-track library for measuring scans and API speed (plan chapter 15).

Usage: .venv/bin/python scripts/bench/make_library.py <out-dir>
Needs ffmpeg. Writes about 1 GB: album/ (2,000 artists x 4 albums x 11 songs: half with cover.jpg,
a quarter with embedded art, a quarter without), chart/ (100 weeks x 100 songs from a pool of
1,500, so the same song repeats) and theme/ (20 x 100). Every file has its own tags.
Set the folder kinds chart -> 차트 and theme -> 테마 before scanning.
"""
import io, os, random, subprocess, sys, tempfile
from multiprocessing import Pool
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC

from PIL import Image

OUT = sys.argv[1]


def _seed() -> bytes:
    """One second of tone, the audio of every file (tags make them different)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "seed.mp3")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                        "-ac", "1", "-ar", "22050", "-b:a", "32k", path], check=True)
        return open(path, "rb").read()


def _cover(i: int) -> bytes:
    buf = io.BytesIO()
    r = random.Random(i)
    Image.new("RGB", (600, 600), (r.randrange(256), r.randrange(256), r.randrange(256))).save(buf, "JPEG", quality=85)
    return buf.getvalue()


seed = _seed()
covers = [_cover(i) for i in range(8)]
SYL = ["하", "늘", "바", "다", "별", "빛", "Neo", "Luna", "Sky", "Moon", "River", "Echo", "도", "시", "새", "봄"]

def name(r, n):
    return "".join(r.choice(SYL) for _ in range(n))

def write(path, tags, cover=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(seed)
    t = EasyID3()
    for k, v in tags.items():
        t[k] = v
    t.save(path)
    if cover:
        id3 = ID3(path)
        id3.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="", data=cover))
        id3.save(path)

def artist_job(a):
    r = random.Random(a)
    artist = f"{name(r, 3)} {a}"
    for b in range(4):
        album = f"{name(r, 2)} 앨범 {a}-{b}"
        d = os.path.join(OUT, "album", artist, album)
        mode = (a + b) % 4  # 0,1: folder cover, 2: embedded, 3: none
        for n in range(1, 12):
            write(os.path.join(d, f"{n:02d} {name(r, 3)}.mp3"),
                  {"title": f"{name(r, 3)} {a}-{b}-{n}", "artist": artist, "album": album,
                   "tracknumber": str(n), "date": str(1990 + a % 35), "genre": r.choice(["Pop", "K-Pop", "Rock", "Jazz", "발라드"])},
                  covers[(a + b) % 8] if mode == 2 else None)
        if mode < 2:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "cover.jpg"), "wb") as f:
                f.write(covers[(a + b) % 8])

def chart_job(w):
    r = random.Random(100000 + w)
    kind, base, count = ("chart", f"멜론/2025-{w:03d}주", 100) if w < 100 else ("theme", f"팝송/테마 {w - 100}", 100)
    for pos in range(1, count + 1):
        s = r.randrange(1500)  # pool of songs: the same song shows up in many weeks
        artist, title = f"가수{s % 400}", f"노래 {s}"
        write(os.path.join(OUT, kind, base, f"{pos:03d} {artist} - {title}.mp3"),
              {"title": title, "artist": artist, "album": f"싱글 {s}", "genre": "K-Pop"}, covers[s % 8] if s % 3 == 0 else None)

if __name__ == "__main__":
    with Pool(12) as p:
        p.map(artist_job, range(2000), chunksize=20)
        p.map(chart_job, range(120))
