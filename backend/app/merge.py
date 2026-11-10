"""Tidying up duplicate artists and genres ("IU" / "아이유 (IU)", "K-Pop" / "kpop").

Artists are suggested by what says they are one (artist_duplicates), each group with its reasons:
the same Bugs artist (bugs_artists.py; merged by themselves when appconf artist_auto_merge is on),
a name the other is also known by (artist_aliases), the same name spelled apart, or the name in the
other's brackets ("아이유 (IU)"; only when the brackets hold another script: "태연 (소녀시대)" is
태연's, not 소녀시대's). Never suggested together: a group and one of its members ("소녀시대"
and "써니 (소녀시대)"), a solo singer and a group, two different Bugs artists, and names an admin
said are not the same (MergeNotSame).

A merge moves everything of the duplicates onto the name kept, and remembers each duplicate's name
in name_aliases: the library is mounted read-only, so the tags keep the old spelling, and the
scanner (scanner._Cache) files songs tagged with it under the kept name, now and in later scans.
Undoing one forgets the alias and has its songs read again by the next scan.
"""

import json
import re
import unicodedata

from sqlalchemy import Text, cast, delete, exists, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from . import search_index
from .models import Album, Artist, Genre, MergeNotSame, NameAlias, Playlist, Track, TrackArtist, TrackGenre
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


def _script(name: str) -> str:
    """Hangul, Latin or other: "태연 (TAEYEON)" is one name twice, "태연 (소녀시대)" a singer and her group."""
    if re.search(r"[가-힣]", name):
        return "hangul"
    return "latin" if re.search(r"[A-Za-z]", name) else "other"


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


def _not_same(db: Session, kind: str) -> set[tuple[str, str]]:
    return {(a, b) for a, b in db.execute(select(MergeNotSame.a, MergeNotSame.b).where(MergeNotSame.kind == kind))}


def mark_not_same(db: Session, kind: str, names: list[str]) -> None:
    """These names are different ones: never suggested together again."""
    names = sorted(set(names))
    rows = [{"kind": kind, "a": a, "b": b} for i, a in enumerate(names) for b in names[i + 1:]]
    if rows:
        db.execute(pg_insert(MergeNotSame).values(rows).on_conflict_do_nothing())
    db.commit()


def forget_not_same(db: Session, kind: str, a: str, b: str) -> None:
    a, b = sorted((a, b))
    db.execute(delete(MergeNotSame).where(MergeNotSame.kind == kind, MergeNotSame.a == a, MergeNotSame.b == b))
    db.commit()


def not_same_list(db: Session, kind: str) -> list[dict]:
    return [{"a": a, "b": b} for a, b in sorted(_not_same(db, kind))]


def artist_duplicates(db: Session) -> list[dict]:
    """Groups of artists that look like one, biggest first: {"items": [...], "reasons": [...]}.
    In each group the one to keep comes first: linked to Bugs, then the most songs."""
    songs = select(TrackArtist.artist_id, func.count().label("n")).group_by(TrackArtist.artist_id).subquery()
    rows = db.execute(select(Artist, func.coalesce(songs.c.n, 0)).outerjoin(songs, songs.c.artist_id == Artist.id)).all()
    items = [r[0] for r in rows]
    count = {r[0].id: int(r[1]) for r in rows}
    refused = _not_same(db, "artist")
    info = {a.id: a.info or {} for a in items}
    related = {  # a group's members and a member's groups, by Bugs id
        a.id: {m["bugs_id"] for k in ("members", "groups") for m in info[a.id].get(k, [])} for a in items
    }

    def blocked(x: Artist, y: Artist) -> bool:
        if tuple(sorted((x.name, y.name))) in refused:
            return True
        if x.bugs_id and y.bugs_id:
            return x.bugs_id != y.bugs_id  # two different Bugs artists (the same: never blocked)
        kx, ky = info[x.id].get("kind"), info[y.id].get("kind")
        if kx and ky and kx != ky:
            return True  # a singer and a group
        return bool((x.bugs_id and x.bugs_id in related[y.id]) or (y.bugs_id and y.bugs_id in related[x.id]))

    reasons_of: dict[tuple[int, int], set[str]] = {}
    # what each is known by: (key, why): its name, its Bugs artist, its other names, its brackets
    by_key: dict[str, list[tuple[int, str]]] = {}
    for i, a in enumerate(items):
        own = {(_key(a.name), "spelling")}
        if a.bugs_id:
            own.add((f"bugs:{a.bugs_id}", "bugs"))
        for other in [o["name"] for o in a.aliases or [] if not o.get("hidden")] + ([a.display_name] if a.display_name else []):
            own.add((_key(other), "alias"))
        m = _PAREN.match(a.name)
        if m:
            own.add((_key(m[1]), "paren"))
            if _script(m[1]) != _script(m[2]):  # "태연 (TAEYEON)": its name in another script
                own.add((_key(m[2]), "paren"))  # (not "태연 (소녀시대)", "Zia (Planetkpop.site)": its group, a site)
        for k, why in own:
            if len(k) >= 2:
                by_key.setdefault(k, []).append((i, why))
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for members in by_key.values():
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                (i, wi), (j, wj) = members[x], members[y]
                if i == j or blocked(items[i], items[j]):
                    continue
                why = "bugs" if "bugs" in (wi, wj) else "alias" if "alias" in (wi, wj) else "paren" if "paren" in (wi, wj) else "spelling"
                reasons_of.setdefault((min(i, j), max(i, j)), set()).add(why)
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # a group's members must all get along (A~B and B~C made it, A and C may be a group and its member)
        if any(blocked(items[i], items[j]) for x, i in enumerate(members) for j in members[x + 1:]):
            continue
        why = set().union(*(r for (i, j), r in reasons_of.items() if i in members and j in members))
        rows = sorted(members, key=lambda i: (items[i].bugs_id is None, -count[items[i].id], items[i].name))
        out.append({
            "reasons": [r for r in ("bugs", "alias", "spelling", "paren") if r in why],
            "items": [
                {"id": items[i].id, "name": items[i].name, "songs": count[items[i].id], "shown": items[i].display_name,
                 "bugs_id": items[i].bugs_id, "bugs": items[i].bugs_source or "pending", "type": info[items[i].id].get("type")}
                for i in rows
            ],
        })
    out.sort(key=lambda g: (g["reasons"][0] != "bugs", -sum(x["songs"] for x in g["items"])))
    return out


def auto_merge(db: Session) -> int:
    """Artists linked to the same Bugs artist, merged into one (the one tagged with Bugs' name,
    else the one with most songs). Returns how many were merged away; 0 while a scan runs."""
    from . import appconf

    if appconf.get("artist_auto_merge") == "off":
        return 0
    refused = _not_same(db, "artist")
    merged = 0
    rows = db.execute(select(Artist.bugs_id).where(Artist.bugs_id.is_not(None)).group_by(Artist.bugs_id).having(func.count() > 1)).all()
    for (bugs_id,) in rows:
        same = list(db.scalars(select(Artist).where(Artist.bugs_id == bugs_id)))
        if any(tuple(sorted((x.name, y.name))) in refused for x in same for y in same if x.id < y.id):
            continue
        songs = dict(db.execute(
            select(TrackArtist.artist_id, func.count()).where(TrackArtist.artist_id.in_([a.id for a in same])).group_by(TrackArtist.artist_id)
        ).all())
        keep = sorted(same, key=lambda a: (_key(a.name) != _key(a.display_name or ""), -songs.get(a.id, 0), a.id))[0]
        try:
            merged += merge(db, "artist", keep.id, [a.id for a in same if a.id != keep.id])
        except Busy:
            return merged
    return merged


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
    # what was found of them: the kept one takes a Bugs link it lacks, and their other names
    linked = next((o for o in others if o.bugs_id), None)
    if keep.bugs_id is None and linked is not None:
        keep.bugs_id, keep.display_name, keep.bugs_source = linked.bugs_id, linked.display_name, linked.bugs_source
        keep.bugs_checked_at, keep.info = linked.bugs_checked_at, linked.info
    found = [(a["name"], a["source"]) for o in [keep, *others] for a in o.aliases or [] if not a.get("hidden")]
    found += [(o.name, "merged") for o in others]
    if found:
        from .artist_aliases import merge as merge_aliases  # (it imports album_notes, which imports the scanner)

        keep.aliases = merge_aliases(keep.aliases, found, keep.name)
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
    # every song's artists (artist_links): theirs become the kept one, once per song
    has_keep = select(TrackArtist.track_id).where(TrackArtist.artist_id == keep.id)
    db.execute(delete(TrackArtist).where(TrackArtist.artist_id.in_(ids), TrackArtist.track_id.in_(has_keep)))
    first = aliased(TrackArtist)  # a song with two of them: the first stays
    db.execute(delete(TrackArtist).where(
        TrackArtist.artist_id.in_(ids),
        exists().where(first.track_id == TrackArtist.track_id, first.artist_id.in_(ids), first.position < TrackArtist.position),
    ))
    db.execute(update(TrackArtist).where(TrackArtist.artist_id.in_(ids)).values(artist_id=keep.id))
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

