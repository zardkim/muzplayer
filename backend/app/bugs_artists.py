"""Artists linked to Bugs, the name the app shows (appconf artist_names: "bugs", or "tag" as tagged).

Bugs is the reference for artists' names, and says whether one is a solo singer or a group, with its
members and the groups a singer is in. An artist gets linked, most sure first:

  1. From an album found on Bugs (album_notes: description_source "bugs:<id>"): its page lists every
     song's artists with their Bugs ids; ours are matched by name (or one of their other names).
  2. By a Bugs artist search: a result named like ours, confirmed by Bugs finding one of our songs
     (or albums) of it under that artist. Several such results and none confirmed: unsure, left to
     the admin (bugs_source "unsure", the results kept in info.candidates). None: "none".
  3. Its Bugs page then gives its name (og:title: "소녀시대" of "소녀시대 (GIRLS' GENERATION)"), the
     other names in brackets (artist_aliases), solo or group, country, debut, members and groups.

Then an artist without a photo gets its Bugs artist's (artist_images.from_bugs).

An admin links one by hand or unlinks it (api/library.py), which later runs leave alone. Run after
the other names (artist_aliases._lookup), a few dozen a run, pausing between requests.
"""

import logging
import re
import time
import urllib.parse
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import appconf, artist_aliases, net, search_index
from .models import Album, Artist, Track, TrackArtist

log = logging.getLogger(__name__)

BUGS = "https://music.bugs.co.kr/"
ALBUM_URL = BUGS + "album/{id}"
ARTIST_URL = BUGS + "artist/{id}"
ARTIST_SEARCH = BUGS + "search/artist?q={q}"
TRACK_SEARCH = BUGS + "search/track?q={q}"
ALBUM_SEARCH = BUGS + "search/album?q={q}"
ALBUMS_PER_RUN = 40
SEARCHES_PER_RUN = 60
PAGES_PER_RUN = 80
PHOTOS_PER_RUN = 80
PAUSE = 0.6
INFO_STALE = timedelta(days=90)
_ID = re.compile(r"/artist/(\d+)")
_MULTI = re.compile(r"'([^']*\|\|[^']*)'")  # openMultiArtist...('Zion.T||Zion.T||80085859||OK\nCrush||Crush||80142603||OK', '')
_PAIR = re.compile(r"^(.*?\S)\s*\(([^()]+)\)$")
_KINDS = (("그룹", "group"), ("듀오", "group"), ("솔로", "solo"))


class Unreachable(Exception):
    pass


def _page(url: str):
    try:
        return net.get_page(url, BUGS)
    except Exception as exc:  # noqa: BLE001 - not answering, moved, blocked: later
        raise Unreachable(str(exc)) from exc


def names_of(bugs_name: str) -> list[str]:
    """"Kenshi Yonezu(켄시 요네즈/米津 玄師)" -> ["Kenshi Yonezu", "켄시 요네즈", "米津 玄師"]. Only names in
    another script: Bugs writes a member as "이수 (엠씨더맥스)", the group in the brackets."""
    name = " ".join(bugs_name.split())
    m = _PAIR.match(name)
    if not m:
        return [name]
    main = m.group(1).strip()
    return [main] + [p.strip() for p in m.group(2).split("/") if p.strip() and search_index.script(p) != search_index.script(main)]


def _bugs_id(href: str | None) -> int | None:
    m = _ID.search(href or "")
    return int(m.group(1)) if m else None


def row_artists(row) -> list[tuple[int, str]]:
    """A Bugs song row's artists: [(bugs id, name)] (several when Bugs lists them in a layer)."""
    more = row.select_one("p.artist a.more")
    if more is not None:
        m = _MULTI.search(more.get("onclick", ""))
        if m:
            out = []
            for part in m.group(1).replace("\\\\n", "\n").replace("\\n", "\n").split("\n"):
                bits = part.split("||")
                if len(bits) >= 3 and bits[2].isdigit():
                    out.append((int(bits[2]), bits[0]))
            if out:
                return out
    return [(i, a.get_text(strip=True)) for a in row.select("p.artist a") if (i := _bugs_id(a.get("href")))]


def _keys(artist: Artist) -> set[str]:
    from .artist_links import key

    return {key(artist.name)} | {key(a) for a in artist_aliases.visible(artist)} - {""}


def _link(artist: Artist, bugs_id: int, name: str, source: str) -> None:
    artist.bugs_id = bugs_id
    artist.display_name = names_of(name)[0][:500]
    artist.bugs_source = source
    artist.bugs_checked_at = datetime.now(UTC)
    artist.info = None  # its page is read next


# ---- 1. albums ----
def link_albums(db: Session) -> int:
    from .artist_links import key

    linked = 0
    albums = db.execute(
        select(Album.id, Album.description_source)
        .where(Album.description_source.like("bugs:%"), Album.bugs_artists_at.is_(None))
        .order_by(Album.id).limit(ALBUMS_PER_RUN)
    ).all()
    for album_id, source in albums:
        bugs_album = source.split(":", 1)[1]
        db.commit()
        page = _page(ALBUM_URL.format(id=bugs_album))
        rows = page.select("tr[trackid]")
        by_no: dict[int, list] = {}
        by_title: dict[str, list] = {}
        for i, row in enumerate(rows, 1):
            no = row.select_one(".trackIndex em")
            n = int(no.get_text(strip=True)) if no and no.get_text(strip=True).isdigit() else i
            title = row.select_one("p.title")
            by_no.setdefault(n, row_artists(row))
            by_title.setdefault(key(title.get_text(" ", strip=True)) if title else "", row_artists(row))
        album_artists = [(i, a.get_text(strip=True)) for a in page.select("table.info a[href*='/artist/']") if (i := _bugs_id(a.get("href")))]
        album = db.get(Album, album_id)
        if album is None:
            continue
        found: list[tuple[Artist, int, str]] = []
        for track in db.scalars(select(Track).where(Track.album_id == album_id)):
            bugs = by_title.get(key(track.title)) or (by_no.get(track.track_no or -1) if len(rows) else None) or []
            ours = db.scalars(select(Artist).join(TrackArtist, TrackArtist.artist_id == Artist.id).where(TrackArtist.track_id == track.id)).all()
            found += _pair(ours, bugs)
        if album.album_artist_id:
            found += _pair([db.get(Artist, album.album_artist_id)], album_artists)
        for artist, bugs_id, name in found:
            if artist.bugs_id is None and artist.bugs_source not in ("manual", "none"):
                _link(artist, bugs_id, name, "album")
                linked += 1
        album.bugs_artists_at = datetime.now(UTC)
        db.commit()
        time.sleep(PAUSE)
    return linked


def _pair(ours: list[Artist], bugs: list[tuple[int, str]]) -> list[tuple[Artist, int, str]]:
    """Ours and Bugs' artists of one song, matched by name (any of each side's names)."""
    from .artist_links import key

    out = []
    for artist in ours:
        if artist is None:
            continue
        mine = _keys(artist)
        hits = [(i, n) for i, n in bugs if mine & {key(x) for x in names_of(n)}]
        if len({i for i, _ in hits}) == 1:
            out.append((artist, *hits[0]))
    return out


# ---- 2. search ----
def candidates(name: str) -> list[dict]:
    """Bugs' artist search for a name: [{"bugs_id", "name", "type"}]."""
    page = _page(ARTIST_SEARCH.format(q=urllib.parse.quote(name)))
    out = []
    for fig in page.select("figure.artistInfo")[:12]:
        title = fig.select_one(".artistTitle")
        link = fig.select_one("a[href*='/artist/']")
        bugs_id = _bugs_id(link.get("href") if link else None)
        if not title or not bugs_id:
            continue
        text = " ".join(fig.get_text(" ", strip=True).split())
        kind = next((k for k in ("그룹", "듀오", "솔로") if k in text), "")
        m = re.search(r"(그룹|듀오|솔로)\s*\(([^)]+)\)", text)
        out.append({"bugs_id": bugs_id, "name": " ".join(title.get_text(" ", strip=True).split()), "type": m.group(0) if m else kind})
    return out


def _confirmed(db: Session, artist: Artist, bugs_id: int) -> bool:
    """Bugs finds one of our songs (or albums) of the artist under that Bugs artist."""
    songs = db.scalars(
        select(Track.title).join(TrackArtist, TrackArtist.track_id == Track.id)
        .where(TrackArtist.artist_id == artist.id, Track.missing_at.is_(None)).limit(2)
    ).all()
    for title in songs:
        page = _page(TRACK_SEARCH.format(q=urllib.parse.quote(f"{title} {artist.name}")))
        if any(bugs_id in {i for i, _ in row_artists(r)} or r.get("artistid") == str(bugs_id) for r in page.select("tr[trackid]")[:10]):
            return True
        time.sleep(PAUSE)
    for title in db.scalars(select(Album.title).where(Album.album_artist_id == artist.id).limit(1)):
        page = _page(ALBUM_SEARCH.format(q=urllib.parse.quote(f"{title} {artist.name}")))
        if any(_bugs_id(a.get("href")) == bugs_id for a in page.select("figure.albumInfo a[href*='/artist/'], .albumInfo a[href*='/artist/']")[:20]):
            return True
    return False


def link_by_search(db: Session) -> int:
    from .artist_links import key

    linked = 0
    has_songs = select(TrackArtist.track_id).where(TrackArtist.artist_id == Artist.id).exists()
    ids = db.scalars(
        select(Artist.id).where(Artist.bugs_id.is_(None), Artist.bugs_source.is_(None), or_(has_songs, Artist.id.in_(select(Album.album_artist_id))))
        .order_by(Artist.id).limit(SEARCHES_PER_RUN)
    ).all()
    for artist_id in ids:
        artist = db.get(Artist, artist_id)
        if artist is None or artist.name.casefold() in ("various artists", "여러 아티스트"):
            if artist is not None:
                artist.bugs_source, artist.bugs_checked_at = "none", datetime.now(UTC)
            continue
        mine = _keys(artist)
        db.commit()
        found = [c for c in candidates(artist.name) if mine & {key(n) for n in names_of(c["name"])}]
        time.sleep(PAUSE)
        sure = [c for c in found if _confirmed(db, artist, c["bugs_id"])] if found else []
        artist = db.get(Artist, artist_id)
        if artist is None or artist.bugs_id is not None:
            continue
        if len(sure) == 1:
            _link(artist, sure[0]["bugs_id"], sure[0]["name"], "search")
            linked += 1
        elif found:
            artist.bugs_source = "unsure"
            artist.info = {**(artist.info or {}), "candidates": found[:8]}
            artist.bugs_checked_at = datetime.now(UTC)
        else:
            artist.bugs_source, artist.bugs_checked_at = "none", datetime.now(UTC)
        db.commit()
        time.sleep(PAUSE)
    return linked


# ---- 3. artist pages ----
def read_page(bugs_id: int) -> dict:
    page = _page(ARTIST_URL.format(id=bugs_id))
    og = page.select_one("meta[property='og:title']")
    title = page.select_one("title")  # "소녀시대 (GIRLS' GENERATION) - 벅스" (the heading may carry badges: "CONNECT …")
    full = re.sub(r"\s*-\s*벅스\s*$", "", " ".join(title.get_text(" ", strip=True).split())) if title else ""
    out: dict = {"name": (og.get("content") or "").strip() if og else "", "full": full}
    image = page.select_one("meta[property='og:image']")
    if image and "/artist/images/" in (image.get("content") or ""):
        out["image"] = image["content"].strip()  # its photo (artist_images.from_bugs)
    for tr in page.select("table.info tr"):
        th, td = tr.select_one("th"), tr.select_one("td")
        if not th or not td:
            continue
        label = th.get_text(strip=True)
        text = " ".join(td.get_text(" ", strip=True).split())
        links = [{"bugs_id": i, "name": " ".join(a.get_text(" ", strip=True).split())} for a in td.select("a[href*='/artist/']") if (i := _bugs_id(a.get("href")))]
        if label == "유형":
            out["type"] = text
            out["kind"] = next((k for word, k in _KINDS if word in text), None)
        elif label == "데뷔":
            out["debut"] = text
        elif label == "국적":
            out["country"] = text
        elif label == "장르":
            out["genre"] = text
        elif label == "멤버":
            out["members"] = links[:30]
        elif label == "소속 활동":
            out["groups"] = links[:30]
    return out


def read_pages(db: Session) -> int:
    done = 0
    ids = db.scalars(
        select(Artist.id).where(Artist.bugs_id.is_not(None), or_(Artist.info.is_(None), Artist.bugs_checked_at < datetime.now(UTC) - INFO_STALE))
        .order_by(Artist.id).limit(PAGES_PER_RUN)
    ).all()
    for artist_id in ids:
        artist = db.get(Artist, artist_id)
        bugs_id = artist.bugs_id if artist else None
        db.commit()
        if bugs_id is None:
            continue
        page = read_page(bugs_id)
        artist = db.get(Artist, artist_id)
        if artist is None or artist.bugs_id != bugs_id:
            continue
        apply_page(artist, page)
        db.commit()
        done += 1
        time.sleep(PAUSE)
    return done


def apply_page(artist: Artist, page: dict) -> None:
    names = names_of(page.get("full") or page.get("name") or "")
    if page.get("name") or names[0]:
        artist.display_name = names_of(page.get("name") or names[0])[0][:500]  # og:title may carry the brackets too
    artist.info = {k: v for k, v in page.items() if k not in ("name", "full") and v}
    artist.bugs_checked_at = datetime.now(UTC)
    # the names in its Bugs brackets: other names of it
    others = [(n, "bugs") for n in names if search_index.norm(n) != search_index.norm(artist.name)]
    if others:  # added to what it has (merge keeps only the hand-made and hidden ones of the old list)
        kept = [(a["name"], a["source"]) for a in artist.aliases or [] if a.get("source") != "manual" and not a.get("hidden")]
        artist.aliases = artist_aliases.merge(artist.aliases, kept + others, artist.name)


def drop_group_names(db: Session) -> int:
    """Once (artist_links.LINKS_VERSION 2): what Bugs' "이수 (엠씨더맥스)" left before names_of knew the
    brackets may hold the group. Other names that are its group, or a Bugs name in the same script as
    its own, are dropped; an artist linked to a Bugs artist only by such a name (our "엠씨더맥스" to Bugs'
    이수) is looked up again."""
    from .artist_links import key
    from .merge import _PAREN

    changed = 0
    for artist in db.scalars(select(Artist).where(or_(Artist.aliases.is_not(None), Artist.bugs_id.is_not(None)))):
        own = artist.display_name or artist.name
        groups = {key(g.get("name") or "") for g in (artist.info or {}).get("groups", [])} - {""}
        aliases = [
            a for a in artist.aliases or []
            if key(a["name"]) not in groups
            and not (a.get("source") == "bugs" and search_index.script(a["name"]) == search_index.script(own) and key(a["name"]) not in (key(own), key(artist.name)))
        ]
        if aliases != (artist.aliases or []):
            artist.aliases = aliases or None
            changed += 1
        if artist.bugs_id and artist.display_name and artist.bugs_source in ("album", "search"):
            m = _PAREN.match(artist.name)
            mine = {key(artist.name), key(m[1]) if m else ""} | {key(a["name"]) for a in aliases if a.get("source") != "bugs"}
            if key(artist.display_name) not in mine and search_index.script(artist.name) == search_index.script(artist.display_name):
                artist.bugs_id = artist.display_name = artist.bugs_source = artist.bugs_checked_at = artist.info = None
                changed += 1
    return changed


# ---- 4. photos ----
def photos(db: Session) -> int:
    """The Bugs artist's photo for the linked artists without one (artist_images.from_bugs)."""
    from . import artist_images

    done = 0
    ids = db.scalars(
        select(Artist.id).where(Artist.bugs_id.is_not(None), Artist.image_path.is_(None), Artist.info.is_not(None)).order_by(Artist.id)
    ).all()
    for artist_id in ids:
        artist = db.get(Artist, artist_id)
        if artist is None or (artist.info or {}).get("photo_missing"):
            continue
        if artist_images.from_bugs(artist):
            done += 1
        db.commit()
        if done >= PHOTOS_PER_RUN:
            break
        time.sleep(PAUSE)
    return done


def run(db: Session) -> int:
    """All four steps, as much as a run does; how many artists got linked, read or a photo."""
    if appconf.get("artist_aliases") == "off":
        return 0
    n = 0
    for step in (link_albums, link_by_search, read_pages, photos):
        try:
            n += step(db)
        except Unreachable as exc:
            log.info("bugs artists: %s not answering (%s), later", step.__name__, exc)
            db.rollback()
            break
    return n


def stats(db: Session) -> dict:
    rows = dict(db.execute(select(func.coalesce(Artist.bugs_source, "pending"), func.count()).group_by(Artist.bugs_source)).all())
    return {
        "linked": sum(v for k, v in rows.items() if k in ("album", "search", "manual")),
        "unsure": rows.get("unsure", 0),
        "none": rows.get("none", 0),
        "pending": rows.get("pending", 0),
    }
