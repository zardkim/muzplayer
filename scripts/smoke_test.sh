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
