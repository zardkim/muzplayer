"""Tidying up duplicate artists and genres ("IU" / "아이유 (IU)", "K-Pop" / "kpop").

A merge moves everything of the duplicates onto the name kept, and remembers each duplicate's name
in name_aliases: the library is mounted read-only, so the tags keep the old spelling, and the
scanner (scanner._Cache) files songs tagged with it under the kept name, now and in later scans.
Undoing one forgets the alias and has its songs read again by the next scan.
"""

import json
import re
import unicodedata

from sqlalchemy import Text, cast, delete, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import search_index
from .models import Album, Artist, Genre, NameAlias, Playlist, Track, TrackGenre
from .scanner import (
    bump_library, carry_album_marks, prune_orphans, remove_covers, scan_lock, update_album_quality,
)

KINDS = ("artist", "genre")
SEP = " / "  # between the artists in Track.artist_text (scanner._apply_tags)
_PAREN = re.compile(r"^(.*?)\s*[(\[]([^)\]]+)[)\]]\s*$")  # "아이유 (IU)" -> "아이유", "IU"


class Busy(Exception):
    """A scan is running (it holds ids of its own)."""


def _key(name: str) -> str:
    """What two spellings of the same name share: width, case, spaces and punctuation ignored."""
    text = unicodedata.normalize("NFKC", name).casefold().replace("&", "and")
    return "".join(c for c in text if c.isalnum())


def _keys(name: str) -> set[str]:
    keys = {_key(name)}
    m = _PAREN.match(name)
    if m:  # also the name outside and inside the brackets
        keys |= {_key(m[1]), _key(m[2])}
    return {k for k in keys if len(k) >= 2}


def _counts(db: Session, kind: str) -> list[tuple[int, str, int]]:
    """(id, name, songs) for every artist or genre."""
    if kind == "artist":
        songs = select(Track.artist_id, func.count().label("n")).group_by(Track.artist_id).subquery()
        rows = db.execute(
            select(Artist.id, Artist.name, func.coalesce(songs.c.n, 0)).outerjoin(songs, songs.c.artist_id == Artist.id)
        ).all()
    else:
        songs = select(TrackGenre.genre_id, func.count().label("n")).group_by(TrackGenre.genre_id).subquery()
        rows = db.execute(
            select(Genre.id, Genre.name, func.coalesce(songs.c.n, 0)).outerjoin(songs, songs.c.genre_id == Genre.id)
        ).all()
    return [(r[0], r[1], int(r[2])) for r in rows]


def duplicates(db: Session, kind: str) -> list[list[dict]]:
    """Groups of names that look like the same artist or genre, biggest first; in each group the
    name with the most songs comes first (the one suggested to keep)."""
    items = _counts(db, kind)
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen: dict[str, int] = {}
    for i, (_, name, _) in enumerate(items):
        for k in _keys(name):
            if k in seen:
                parent[find(i)] = find(seen[k])
            else:
                seen[k] = i
    groups: dict[int, list[int]] = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    out = [
        sorted(({"id": items[i][0], "name": items[i][1], "songs": items[i][2]} for i in members),
               key=lambda x: (-x["songs"], x["name"]))
        for members in groups.values() if len(members) > 1
    ]
    out.sort(key=lambda g: -sum(x["songs"] for x in g))
    return out


def _set_alias(db: Session, kind: str, names: list[str], target: str) -> None:
    """The duplicates' names (and names merged into them before) now go to target."""
    db.execute(update(NameAlias).where(NameAlias.kind == kind, NameAlias.target.in_(names)).values(target=target))
    db.execute(delete(NameAlias).where(NameAlias.kind == kind, NameAlias.name == target))  # merged back the other way
    for name in names:
        db.execute(
            pg_insert(NameAlias).values(kind=kind, name=name, target=target)
            .on_conflict_do_update(index_elements=["kind", "name"], set_={"target": target})
        )


def _rewrite_rules(db: Session, field: str, names: list[str], target: str) -> None:
    """Smart playlists that named a duplicate name the kept one (their rules match by name)."""
    lowered = {n.lower() for n in names}
    for playlist in db.scalars(select(Playlist).where(Playlist.rules.is_not(None))):
        rules = json.loads(json.dumps(playlist.rules))  # a copy: a JSON column sees only a new value
        hits = [
            r for r in rules.get("rules", [])
            if r.get("field") == field and isinstance(r.get("value"), str) and r["value"].strip().lower() in lowered
        ]
        for rule in hits:
            rule["value"] = target
        if hits:
            playlist.rules = rules


def merge(db: Session, kind: str, keep_id: int, ids: list[int]) -> int:
    """Merges the artists or genres `ids` into `keep_id`. Returns how many were merged.
    Raises Busy while a scan runs, LookupError for an unknown id."""
    lock = scan_lock()
    if not lock.acquire(blocking=False):
        raise Busy
    try:
        ids = [i for i in dict.fromkeys(ids) if i != keep_id]
        model = Artist if kind == "artist" else Genre
        keep = db.get(model, keep_id)
        others = list(db.scalars(select(model).where(model.id.in_(ids))))
        if keep is None or len(others) != len(ids):
            raise LookupError
        if not others:
            return 0
        names = [o.name for o in others]
        _set_alias(db, kind, names, keep.name)
        if kind == "artist":
            _merge_artists(db, keep, others)
        else:
            _merge_genres(db, keep, others)
        _rewrite_rules(db, kind, names, keep.name)
        search_index.index_albums_artists(db)
        update_album_quality(db)
        bump_library(db)
        db.commit()
        return len(others)
    finally:
        lock.release()


def _merge_genres(db: Session, keep: Genre, others: list[Genre]) -> None:
    ids = [o.id for o in others]
    songs = select(TrackGenre.track_id, literal(keep.id)).where(TrackGenre.genre_id.in_(ids))
    db.execute(pg_insert(TrackGenre).from_select(["track_id", "genre_id"], songs).on_conflict_do_nothing())
    db.execute(delete(TrackGenre).where(TrackGenre.genre_id.in_(ids)))
    db.execute(delete(Genre).where(Genre.id.in_(ids)))


def _merge_artists(db: Session, keep: Artist, others: list[Artist]) -> None:
    ids = [o.id for o in others]
    names = {o.name for o in others}
    # the artist text songs show (and search, and smart playlists match): the kept spelling
    like = or_(*(Track.artist_text.contains(n, autoescape=True) for n in names))
    for track, album_title in db.execute(
        select(Track, Album.title).outerjoin(Album, Album.id == Track.album_id).where(or_(Track.artist_id.in_(ids), like))
    ):
        parts = [keep.name if p in names else p for p in track.artist_text.split(SEP)]
        text = SEP.join(dict.fromkeys(parts))[:1000]
        if text != track.artist_text:
            track.artist_text = text
            track.search_text = search_index.index_text(track.title, text, album_title)
    db.execute(update(Track).where(Track.artist_id.in_(ids)).values(artist_id=keep.id))
    # their albums: under the kept artist; one it already has with the same title takes the songs
    taken = {(a.kind, a.title): a.id for a in db.scalars(select(Album).where(Album.album_artist_id == keep.id))}
    moves: dict[int, int] = {}
    for album in db.scalars(select(Album).where(Album.album_artist_id.in_(ids)).order_by(Album.id)):
        same = taken.get((album.kind, album.title))
        if same is None:
            album.album_artist_id = keep.id
            taken[(album.kind, album.title)] = album.id
            db.flush()  # one at a time: (kind, artist, title) is unique
        else:
            moves[album.id] = same
            db.execute(update(Track).where(Track.album_id == album.id).values(album_id=same))
    if not keep.image_path:  # the kept one has no photo yet: look again (artist_images)
        keep.image_checked_at = None
    db.flush()
    carry_album_marks(db, moves)
    remove_covers(prune_orphans(db, moves))


def aliases(db: Session, kind: str) -> list[dict]:
    return [
        {"name": a.name, "target": a.target}
        for a in db.scalars(select(NameAlias).where(NameAlias.kind == kind).order_by(NameAlias.target, NameAlias.name))
    ]


def unmerge(db: Session, kind: str, name: str) -> bool:
    """Forgets a merge: songs tagged `name` are read again (by the scan the caller starts) and filed
    under that name once more. False when there was no such alias."""
    lock = scan_lock()
    if not lock.acquire(blocking=False):
        raise Busy
    try:
        gone = db.execute(delete(NameAlias).where(NameAlias.kind == kind, NameAlias.name == name)).rowcount
        if not gone:
            return False
        # their tags still say `name`: a changed modification time makes the scan read them again
        tag = cast(Track.tag_json, Text)
        forms = {json.dumps(name)[1:-1], json.dumps(name, ensure_ascii=False)[1:-1]}  # as stored: escaped or not
        db.execute(update(Track).where(or_(*(tag.contains(f, autoescape=True) for f in forms))).values(file_mtime=0))
        db.commit()
        return True
    finally:
        lock.release()

