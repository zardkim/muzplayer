#!/bin/bash
# API smoke test against a running instance.
# Usage: scripts/smoke_test.sh <base-url> <admin-user> <admin-password> <music-dir-on-host>
# Use a TEST library only: it temporarily moves one .mp3 out of the music folder and
# leaves a disabled user named "smokeuser".
set -u
BASE="${1:?base url}/api/v1"; ADMIN="$2"; ADMIN_PW="$3"; MUSIC="$4"
TMP=$(mktemp -d)
MOVED=""
cleanup() { [ -n "$MOVED" ] && [ -f "$TMP/moved.mp3" ] && mv "$TMP/moved.mp3" "$MOVED"; rm -rf "$TMP"; }
trap cleanup EXIT INT TERM
A="$TMP/admin.txt"; U="$TMP/user.txt"
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (expected '$3', got '$2')"; fail=1; fi; }
j() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
login() { curl -s -c "$1" -o /dev/null -w '%{http_code}' -X POST "$BASE/auth/login" -H 'content-type: application/json' -d "{\"username\":\"$2\",\"password\":\"$3\"}"; }
scan() {
  id=$(curl -s -b "$A" -X POST "$BASE/admin/scan" | j 'd["id"]')
  for _ in $(seq 1 60); do
    st=$(curl -s -b "$A" "$BASE/admin/scan/$id" | j 'd["status"]'); [ "$st" != running ] && break; sleep 1
  done
  echo "$st"
}

check "admin login" "$(login "$A" "$ADMIN" "$ADMIN_PW")" 200
check "login cookie is HttpOnly" "$(grep -c '#HttpOnly_' "$A")" 1
check "unauthenticated is 401" "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/tracks")" 401
check "scan finishes" "$(scan)" done
total=$(curl -s -b "$A" "$BASE/tracks" | j 'd["total"]')
[ "$total" -gt 0 ] && echo "ok   tracks indexed ($total)" || { echo "FAIL no tracks"; fail=1; }
tid=$(curl -s -b "$A" "$BASE/tracks?sort=title" | j 'd["items"][0]["id"]')
check "range request returns 206" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -H 'Range: bytes=0-99' "$BASE/tracks/$tid/stream")" 206
check "cover available" "$(curl -s -b "$A" "$BASE/albums" | j 'any(a["has_cover"] for a in d["items"])')" True
cov=$(curl -s -b "$A" "$BASE/albums?limit=500" | j 'next(str(a["id"]) + "&v=" + str(a["cover_v"]) for a in d["items"] if a["has_cover"])')
cover_url="$BASE/albums/${cov%%&*}/cover?size=thumb&${cov#*&}"
check "versioned cover cached for a year" "$(curl -s -b "$A" -o /dev/null -D - "$cover_url" | grep -ci 'immutable')" 1
etag=$(curl -s -b "$A" -o /dev/null -D - "$cover_url" | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r')
check "unchanged cover is 304" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -H "If-None-Match: $etag" "$cover_url")" 304
list_etag() { curl -s -b "$A" -o /dev/null -D - "$BASE/albums" | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r'; }
etag1=$(list_etag)
check "unchanged album list is 304" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -H "If-None-Match: $etag1" "$BASE/albums")" 304
word=$(curl -s -b "$A" "$BASE/tracks?sort=title" | j 'd["items"][0]["title"].split()[0][:4]')
check "search finds a song" "$(curl -s -b "$A" -G --data-urlencode "q=$word" "$BASE/tracks" | j 'd["total"] > 0')" True
curl -s -b "$A" -o /dev/null -X PUT "$BASE/favorites/$tid"
check "favorites list" "$(curl -s -b "$A" "$BASE/favorites" | j '[t["id"] for t in d["items"]].count('"$tid"')')" 1
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/favorites/$tid"
check "charts list" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/charts")" 200
check "charts & themes page" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/collections/home")" 200
check "folder kinds list" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/admin/folders")" 200

# second user cannot see the first user's playlist
curl -s -b "$A" -o /dev/null -X POST "$BASE/admin/users" -H 'content-type: application/json' -d '{"username":"smokeuser","password":"smokepass1"}'
uid=$(curl -s -b "$A" "$BASE/admin/users" | j '[u["id"] for u in d["items"] if u["username"]=="smokeuser"][0]')
curl -s -b "$A" -o /dev/null -X PATCH "$BASE/admin/users/$uid" -H 'content-type: application/json' -d '{"is_active":true,"password":"smokepass1"}'
check "second user login" "$(login "$U" smokeuser smokepass1)" 200
pid=$(curl -s -b "$A" -X POST "$BASE/playlists" -H 'content-type: application/json' -d '{"name":"smoke"}' | j 'd["id"]')
curl -s -b "$A" -o /dev/null -X POST "$BASE/playlists/$pid/tracks" -H 'content-type: application/json' -d "{\"track_ids\":[$tid]}"
check "other user's playlist is 404" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/playlists/$pid")" 404
check "other user's playlist list empty" "$(curl -s -b "$U" "$BASE/playlists" | j 'len(d["items"])')" 0

# stars, likes, play counts, mixes and smart playlists are each user's own
aid=$(curl -s -b "$A" "$BASE/tracks?sort=title" | j 'd["items"][0]["album_id"]')
curl -s -b "$A" -o /dev/null -X PUT "$BASE/ratings/tracks/$tid" -H 'content-type: application/json' -d '{"rating":5}'
curl -s -b "$A" -o /dev/null -X PUT "$BASE/ratings/albums/$aid" -H 'content-type: application/json' -d '{"rating":4}'
curl -s -b "$A" -o /dev/null -X PUT "$BASE/favorites/albums/$aid"
check "song stars saved" "$(curl -s -b "$A" "$BASE/tracks?sort=title" | j 'd["items"][0]["rating"]')" 5
check "other user's song stars separate" "$(curl -s -b "$U" "$BASE/tracks?sort=title" | j 'd["items"][0]["rating"]')" None
check "album stars and like" "$(curl -s -b "$A" "$BASE/albums/$aid" | j '(d["rating"], d["is_favorite"])')" "(4, True)"
check "other user's album marks separate" "$(curl -s -b "$U" "$BASE/albums/$aid" | j '(d["rating"], d["is_favorite"])')" "(None, False)"
curl -s -b "$A" -o /dev/null -X POST "$BASE/history" -H 'content-type: application/json' -d "{\"track_id\":$tid}"
check "play counted in most played mix" "$(curl -s -b "$A" "$BASE/mixes/top" | j "$tid in [t['id'] for t in d['tracks']]")" True
check "random mix" "$(curl -s -b "$A" "$BASE/mixes/random" | j 'len(d["tracks"]) > 0')" True
sid=$(curl -s -b "$A" -X POST "$BASE/playlists" -H 'content-type: application/json' -d '{"name":"smoke smart","rules":{"match":"all","rules":[{"field":"rating","op":"gte","value":5}],"sort":"title","limit":50}}' | j 'd["id"]')
check "smart playlist follows its rules" "$(curl -s -b "$A" "$BASE/playlists/$sid" | j "$tid in [e['track']['id'] for e in d['entries']]")" True
check "songs can't be put in a smart playlist" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/playlists/$sid/tracks" -H 'content-type: application/json' -d "{\"track_ids\":[$tid]}")" 400
check "video needs a YouTube link" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/videos" -H 'content-type: application/json' -d "{\"video\":\"not a youtube link\",\"kind\":\"mv\",\"album_id\":$aid}")" 400
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/playlists/$sid"

# audiobooks (only when AUDIOBOOK_PATH is set): stream, and positions kept per user
if [ "$(curl -s "$BASE/config" | j 'd["audiobooks"]')" = True ]; then
  bid=$(curl -s -b "$A" "$BASE/books?sort=title" | j 'd["items"][0]["id"] if d["items"] else ""')
  if [ -n "$bid" ]; then
    check "book stream range 206" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -H 'Range: bytes=0-99' "$BASE/books/$bid/files/0/stream")" 206
    curl -s -b "$A" -o /dev/null -X PUT "$BASE/books/$bid/progress" -H 'content-type: application/json' -d '{"position":3}'
    check "book position saved" "$(curl -s -b "$A" "$BASE/books/$bid" | j 'd["progress"]["position"]')" 3.0
    check "other user's book position separate" "$(curl -s -b "$U" "$BASE/books/$bid" | j 'd["progress"]')" None
    curl -s -b "$A" -o /dev/null -X DELETE "$BASE/books/$bid/progress"
  else
    echo "FAIL audiobooks on but no books indexed"; fail=1
  fi
fi

# removing a file hides it but keeps it in playlists
path=$(find "$MUSIC" -type f -name '*.mp3' | head -1)
MOVED="$path"
mv "$path" "$TMP/moved.mp3"
check "rescan after delete" "$(scan)" done
# the job count, not the list total: the file may be a duplicate chart copy that lists never showed
check "missing track detected" "$(curl -s -b "$A" "$BASE/admin/scan/latest" | j 'd["job"]["missing"]')" 1
check "lists change after a scan with changes" "$([ "$(list_etag)" != "$etag1" ] && echo changed)" changed
check "playlist keeps entry" "$(curl -s -b "$A" "$BASE/playlists/$pid" | j 'len(d["entries"])')" 1
mv "$TMP/moved.mp3" "$path"
MOVED=""
check "rescan after restore" "$(scan)" done
check "restored track visible" "$(curl -s -b "$A" "$BASE/tracks" | j 'd["total"]')" "$total"

# cleanup
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/playlists/$pid"
curl -s -b "$A" -o /dev/null -X PATCH "$BASE/admin/users/$uid" -H 'content-type: application/json' -d '{"is_active":false}'
check "disabled user session revoked" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/auth/me")" 401
exit $fail
