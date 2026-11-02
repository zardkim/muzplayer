#!/bin/bash
# API smoke test against a running instance.
# Usage: scripts/smoke_test.sh <base-url> <admin-user> <admin-password> <music-dir-on-host>
# On a fresh install the admin is made here first (the first account is the admin).
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
scan() {  # optional: a JSON body, e.g. '{"folder":"album","mode":"rescan"}'
  body=${1:-}; [ -n "$body" ] || body='{}'
  id=$(curl -s -b "$A" -X POST "$BASE/admin/scan" -H 'content-type: application/json' -d "$body" | j 'd["id"]')
  for _ in $(seq 1 60); do
    st=$(curl -s -b "$A" "$BASE/admin/scan/$id" | j 'd["status"]'); [ "$st" != running ] && break; sleep 1
  done
  echo "$st"
}

setup() { curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/auth/setup" -H 'content-type: application/json' -d "{\"username\":\"$1\",\"password\":\"$2\"}"; }
if [ "$(curl -s "$BASE/config" | j 'd["needs_setup"]')" = True ]; then
  check "first account is made (admin)" "$(setup "$ADMIN" "$ADMIN_PW")" 201
fi
check "setup is closed once an account exists" "$(setup intruder intruder-pw)" 409
check "config no longer asks for setup" "$(curl -s "$BASE/config" | j 'd["needs_setup"]')" False
check "admin login" "$(login "$A" "$ADMIN" "$ADMIN_PW")" 200
check "login cookie is HttpOnly" "$(grep -c '#HttpOnly_' "$A")" 1
check "unauthenticated is 401" "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/tracks")" 401
check "scan finishes" "$(scan)" done
# service keys: set in the app, never sent back, take effect at once
put_keys() { curl -s -b "$A" -X PUT "$BASE/admin/integrations" -H 'content-type: application/json' -d "$1"; }
check "youtube key saved" "$(put_keys '{"youtube_api_key":"smoke-test-key-123"}' | j 'd["youtube_api_key_set"]')" True
check "key is not sent back" "$(curl -s -b "$A" "$BASE/admin/integrations" | grep -c smoke-test-key-123)" 0
check "youtube search on without restart" "$(curl -s "$BASE/config" | j 'd["youtube_search"]')" True
check "youtube key cleared" "$(put_keys '{"youtube_api_key":""}' | j 'd["youtube_search"]')" False
total=$(curl -s -b "$A" "$BASE/tracks" | j 'd["total"]')
[ "$total" -gt 0 ] && echo "ok   tracks indexed ($total)" || { echo "FAIL no tracks"; fail=1; }
tid=$(curl -s -b "$A" "$BASE/tracks?sort=title" | j 'd["items"][0]["id"]')
check "range request returns 206" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -H 'Range: bytes=0-99' "$BASE/tracks/$tid/stream")" 206
# converting (ffmpeg in the image): a song above 128 kbps, finished file with byte ranges
if [ "$(curl -s "$BASE/config" | j 'd.get("transcode")')" = True ]; then
  big=$(curl -s -b "$A" "$BASE/tracks?limit=500" | j 'next((str(t["id"]) for t in d["items"] if (t.get("bitrate") or 0) > 200), "")')
  if [ -n "$big" ]; then
    check "converted stream is mp3" "$(curl -s -b "$A" -o /dev/null -w '%{content_type}' "$BASE/tracks/$big/stream?quality=128")" audio/mpeg
    check "converted file range 206" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -H 'Range: bytes=0-99' "$BASE/tracks/$big/stream?quality=128&whole=1")" 206
  else
    echo "skip converting (no song above 200 kbps)"
  fi
else
  echo "FAIL ffmpeg missing (config transcode false)"; fail=1
fi
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
# the search index: every word, in any order, any case, across title/artist/album
fid=$(curl -s -b "$A" "$BASE/tracks?sort=title" | j 'd["items"][0]["id"]')
q2=$(curl -s -b "$A" "$BASE/tracks?sort=title" | j '(d["items"][0]["artist"] or "")[:20].upper() + " " + d["items"][0]["title"][:20]')
check "search: artist and title, any order and case" "$(curl -s -b "$A" -G --data-urlencode "q=$q2" --data-urlencode sort=relevance "$BASE/tracks" | j "$fid in [t['id'] for t in d['items']]")" True
check "search index built" "$(curl -s -b "$A" "$BASE/admin/scan/latest" | j 'd["search_index_ready"]')" True
# lyrics: the song's own, else looked up once (needs the internet: only the shape is checked) and kept
check "lyrics answer" "$(curl -s -b "$A" "$BASE/tracks/$fid/lyrics" | j 'sorted(d)')" "['plain', 'synced']"
check "lyrics answer again" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/tracks/$fid/lyrics")" 200
check "search box suggests words" "$(curl -s -b "$A" "$BASE/search/suggest?q=a" | j 'sorted(d)')" "['items']"
check "songs say whether they have lyrics" "$(curl -s -b "$A" "$BASE/tracks?limit=1" | j '"has_lyrics" in d["items"][0]')" True
curl -s -b "$A" -o /dev/null -X PUT "$BASE/favorites/$tid"
check "favorites list" "$(curl -s -b "$A" "$BASE/favorites" | j '[t["id"] for t in d["items"]].count('"$tid"')')" 1
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/favorites/$tid"
check "charts list" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/charts")" 200
check "charts & themes page" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/collections/home")" 200
check "folder kinds list" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/admin/folders")" 200
# one folder: rescan reads every file again and keeps the songs (ids); reset is announced with what it takes
top=$(curl -s -b "$A" "$BASE/admin/folders" | j '[f["path"] for f in d["items"] if f["present"] and f["track_count"]][0]')
ids_before=$(curl -s -b "$A" "$BASE/tracks?limit=500" | j 'sorted(t["id"] for t in d["items"])')
check "folder rescan" "$(scan "{\"folder\":\"$top\",\"mode\":\"rescan\"}")" done
check "folder rescan keeps song ids" "$(curl -s -b "$A" "$BASE/tracks?limit=500" | j 'sorted(t["id"] for t in d["items"])')" "$ids_before"
check "rescan of everything is refused" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/admin/scan" -H 'content-type: application/json' -d '{"mode":"reset"}')" 400
check "reset impact counted" "$(curl -s -b "$A" -G --data-urlencode "path=$top" "$BASE/admin/folders/impact" | j 'd["tracks"] > 0')" True
check "genres carry cover albums" "$(curl -s -b "$A" "$BASE/genres" | j 'all("covers" in g for g in d["items"])')" True
check "folder view lists the top folders" "$(curl -s -b "$A" "$BASE/folders" | j 'len(d["folders"]) > 0')" True
# down the first subfolder until a level holds songs
fpath=""; ftracks=0
for _ in 1 2 3 4 5 6; do
  level=$(curl -s -b "$A" -G --data-urlencode "path=$fpath" "$BASE/folders")
  ftracks=$(echo "$level" | j 'len(d["tracks"])')
  [ "$ftracks" -gt 0 ] && break
  fpath=$(echo "$level" | j 'd["folders"][0]["path"] if d["folders"] else ""')
  [ -z "$fpath" ] && break
done
check "folder view reaches songs" "$([ "$ftracks" -gt 0 ] && echo yes)" yes
check "artist photo status" "$(curl -s -b "$A" "$BASE/admin/artist-images/status" | j '"with_photo" in d')" True
check "model list needs a saved key" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/admin/integrations/models?provider=gemini")" 400

# second user cannot see the first user's playlist
curl -s -b "$A" -o /dev/null -X POST "$BASE/admin/users" -H 'content-type: application/json' -d '{"username":"smokeuser","password":"smokepass1"}'
uid=$(curl -s -b "$A" "$BASE/admin/users" | j '[u["id"] for u in d["items"] if u["username"]=="smokeuser"][0]')
curl -s -b "$A" -o /dev/null -X PATCH "$BASE/admin/users/$uid" -H 'content-type: application/json' -d '{"is_active":true,"password":"smokepass1"}'
check "second user login" "$(login "$U" smokeuser smokepass1)" 200
curl -s -b "$U" -o /dev/null "$BASE/auth/me"
check "signed-in user shows online" "$(curl -s -b "$A" "$BASE/admin/users" | j '[u["online"] for u in d["items"] if u["username"]=="smokeuser"][0]')" True
check "log has the sign-in" "$(curl -s -b "$A" "$BASE/admin/logs?kind=login&q=smokeuser" | j 'd["items"][0]["action"]')" login
check "log has the admin change" "$(curl -s -b "$A" "$BASE/admin/logs?kind=admin&q=smokeuser" | j '"PATCH /admin/users/{user_id}" in d["items"][0]["detail"]')" True
check "log is admin-only" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/admin/logs")" 403
pid=$(curl -s -b "$A" -X POST "$BASE/playlists" -H 'content-type: application/json' -d '{"name":"smoke"}' | j 'd["id"]')
curl -s -b "$A" -o /dev/null -X POST "$BASE/playlists/$pid/tracks" -H 'content-type: application/json' -d "{\"track_ids\":[$tid]}"
check "a song already in a playlist isn't added twice" "$(curl -s -b "$A" -X POST "$BASE/playlists/$pid/tracks" -H 'content-type: application/json' -d "{\"track_ids\":[$tid]}" | j '[d["added"], d["skipped"]]')" "[0, 1]"
check "a playlist name of spaces is refused" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X PATCH "$BASE/playlists/$pid" -H 'content-type: application/json' -d '{"name":"   "}')" 422
check "other user's playlist is 404" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/playlists/$pid")" 404
check "other user's playlists don't show mine" "$(curl -s -b "$U" "$BASE/playlists" | j "$pid in [p['id'] for p in d['items']]")" False
check "settings are kept with the account" "$(curl -s -b "$U" -X PATCH "$BASE/auth/me" -H 'content-type: application/json' -d '{"prefs":{"v":1,"t":1,"theme":"spotify"}}' >/dev/null; curl -s -b "$U" "$BASE/auth/me" | j 'd["prefs"]["theme"]')" spotify
check "everyone has a default playlist" "$(curl -s -b "$U" "$BASE/playlists" | j '[p["is_default"] for p in d["items"]]')" "[True]"
dpl=$(curl -s -b "$U" "$BASE/playlists" | j 'd["items"][0]["id"]')
check "the default playlist can't be deleted" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/playlists/$dpl")" 400
check "everyone has a default video playlist" "$(curl -s -b "$U" "$BASE/video-playlists" | j '[p["is_default"] for p in d["items"]]')" "[True]"

# user switching: two accounts on one device; switching into an admin account asks for its password
D="$TMP/device.txt"; cp "$U" "$D"
sw() { curl -s -b "$D" -c "$D" -o /dev/null -w '%{http_code}' -X POST "$BASE/auth/switch" -H 'content-type: application/json' -d "$1"; }
curl -s -b "$D" -c "$D" -o /dev/null -X POST "$BASE/auth/login" -H 'content-type: application/json' -d "{\"username\":\"$ADMIN\",\"password\":\"$ADMIN_PW\",\"add\":true}"
check "added account listed for switching" "$(curl -s -b "$D" -c "$D" "$BASE/auth/accounts" | j '[a["username"] for a in d]')" "['smokeuser']"
admin_id=$(curl -s -b "$D" "$BASE/auth/me" | j 'd["id"]')
check "switch to a user needs no password" "$(sw "{\"user_id\":$uid}")" 200
check "switch to admin needs its password" "$(sw "{\"user_id\":$admin_id}")" 403
check "switch to admin, wrong password" "$(sw "{\"user_id\":$admin_id,\"password\":\"wrong-password\"}")" 401
check "switch to admin with password" "$(sw "{\"user_id\":$admin_id,\"password\":\"$ADMIN_PW\"}")" 200
check "switched account" "$(curl -s -b "$D" "$BASE/auth/me" | j 'd["username"]')" "$ADMIN"
check "switch to an account not on this device" "$(sw '{"user_id":999999}')" 404

# AI playlists: without a key, a clear code (with one, it would cost a request)
if [ "$(curl -s "$BASE/config" | j 'd.get("ai_playlists")')" = False ]; then
  check "ai playlist without a key" "$(curl -s -b "$U" -X POST "$BASE/playlists/ai" -H 'content-type: application/json' -d '{"prompt":"rainy day"}' | j 'd["detail"]')" ai_not_configured
fi

# stars, likes, play counts, mixes and smart playlists are each user's own
aid=$(curl -s -b "$A" "$BASE/tracks?sort=title" | j 'd["items"][0]["album_id"]')
curl -s -b "$A" -o /dev/null -X PUT "$BASE/ratings/tracks/$tid" -H 'content-type: application/json' -d '{"rating":5}'
curl -s -b "$A" -o /dev/null -X PUT "$BASE/ratings/albums/$aid" -H 'content-type: application/json' -d '{"rating":4}'
curl -s -b "$A" -o /dev/null -X PUT "$BASE/favorites/albums/$aid"
check "song stars saved" "$(curl -s -b "$A" "$BASE/tracks?sort=title" | j 'd["items"][0]["rating"]')" 5.0
check "other user's song stars separate" "$(curl -s -b "$U" "$BASE/tracks?sort=title" | j 'd["items"][0]["rating"]')" None
check "album stars and like" "$(curl -s -b "$A" "$BASE/albums/$aid" | j '(d["rating"], d["is_favorite"])')" "(4.0, True)"
check "half stars allowed" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X PUT "$BASE/ratings/albums/$aid" -H 'content-type: application/json' -d '{"rating":3.5}')/$(curl -s -b "$A" "$BASE/albums/$aid" | j 'd["rating"]')" "204/3.5"
check "other steps refused" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X PUT "$BASE/ratings/albums/$aid" -H 'content-type: application/json' -d '{"rating":3.3}')" 422
curl -s -b "$A" -o /dev/null -X PUT "$BASE/ratings/albums/$aid" -H 'content-type: application/json' -d '{"rating":4}'
check "other user's album marks separate" "$(curl -s -b "$U" "$BASE/albums/$aid" | j '(d["rating"], d["is_favorite"])')" "(None, False)"
h0=$(curl -s -b "$U" "$BASE/history?limit=1000" | j 'len(d["items"])')
curl -s -b "$U" -o /dev/null -X PATCH "$BASE/auth/me" -H 'content-type: application/json' -d '{"record_history":false}'
curl -s -b "$U" -o /dev/null -X POST "$BASE/history" -H 'content-type: application/json' -d "{\"track_id\":$tid}"
check "private listening keeps no history" "$(curl -s -b "$U" "$BASE/history?limit=1000" | j 'len(d["items"])')" "$h0"
check "radio finds similar songs" "$(curl -s -b "$U" "$BASE/radio?track_id=$tid&limit=5" | j 'len(d["tracks"]) > 0 and all(t["id"] != '"$tid"' for t in d["tracks"])')" True
curl -s -b "$U" -o /dev/null -X PATCH "$BASE/auth/me" -H 'content-type: application/json' -d '{"record_history":true}'
curl -s -b "$A" -o /dev/null -X POST "$BASE/history" -H 'content-type: application/json' -d "{\"track_id\":$tid}"
check "play counted in most played mix" "$(curl -s -b "$A" "$BASE/mixes/top" | j "$tid in [t['id'] for t in d['tracks']]")" True
check "random mix" "$(curl -s -b "$A" "$BASE/mixes/random" | j 'len(d["tracks"]) > 0')" True
sid=$(curl -s -b "$A" -X POST "$BASE/playlists" -H 'content-type: application/json' -d '{"name":"smoke smart","rules":{"match":"all","rules":[{"field":"rating","op":"gte","value":5}],"sort":"title","limit":50}}' | j 'd["id"]')
check "smart playlist follows its rules" "$(curl -s -b "$A" "$BASE/playlists/$sid" | j "$tid in [e['track']['id'] for e in d['entries']]")" True
check "songs can't be put in a smart playlist" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/playlists/$sid/tracks" -H 'content-type: application/json' -d "{\"track_ids\":[$tid]}")" 400
check "video needs a YouTube link" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/videos" -H 'content-type: application/json' -d "{\"video\":\"not a youtube link\",\"kind\":\"mv\",\"album_id\":$aid}")" 400
check "music videos page lists videos" "$(curl -s -b "$A" "$BASE/videos?kind=mv" | j 'sorted(d)')" "['items', 'total']"
check "music videos can be searched" "$(curl -s -b "$A" "$BASE/videos?q=nothing-matches-this&kind=concert" | j 'd["total"]')" 0
vpl=$(curl -s -b "$A" -X POST "$BASE/video-playlists" -H 'content-type: application/json' -d '{"name":"smoke videos"}' | j 'd["id"]')
check "video playlist made" "$(curl -s -b "$A" "$BASE/video-playlists/$vpl" | j '[d["name"], d["count"]]')" "['smoke videos', 0]"
check "video playlist deleted" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/video-playlists/$vpl")" 204
check "no thumbnail for a video that isn't there" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/videos/999999/thumb")" 404
check "only an admin adds YouTube videos" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X POST "$BASE/videos" -H 'content-type: application/json' -d "{\"video\":\"dQw4w9WgXcQ\",\"kind\":\"mv\",\"album_id\":$aid}")" 403
check "only an admin registers NAS videos" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/videos/files")" 403
check "NAS video files answer" "$(curl -s -b "$A" "$BASE/videos/files" | j 'sorted(d)')" "['folder', 'items']"
check "only NAS videos are linked by name" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/videos/999999/link" -H 'content-type: application/json' -d '{"auto":true}')" 404
check "liking a video that isn't there" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X PUT "$BASE/videos/999999/favorite")" 404
check "no similar videos of a video that isn't there" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/videos/999999/related")" 404
check "liked videos answer" "$(curl -s -b "$A" "$BASE/videos?liked=true" | j 'sorted(d)')" "['items', 'total']"
check "NAS video path stays in the video folder" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/videos/files" -H 'content-type: application/json' -d '{"path":"../music","kind":"mv"}')" 404
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/playlists/$sid"

# sign-up: closed by default; with approval an account waits, then logs in once approved
J="$TMP/join.txt"
signup() { curl -s -c "$J" -o /dev/null -w '%{http_code}' -X POST "$BASE/auth/signup" -H 'content-type: application/json' -d "{\"username\":\"$1\",\"password\":\"joinpass123\"}"; }
check "sign-up closed by default" "$(signup smokejoin1)" 403
curl -s -b "$A" -o /dev/null -X PUT "$BASE/admin/signup" -H 'content-type: application/json' -d '{"mode":"approval"}'
check "sign-up mode shown to the login page" "$(curl -s "$BASE/config" | j 'd["signup"]')" approval
check "sign-up asks for approval" "$(signup smokejoin1)" 201
check "waiting account can't log in" "$(curl -s -X POST "$BASE/auth/login" -H 'content-type: application/json' -d '{"username":"smokejoin1","password":"joinpass123"}' | j 'd["detail"]')" pending_approval
jid=$(curl -s -b "$A" "$BASE/admin/users" | j '[u["id"] for u in d["items"] if u["username"]=="smokejoin1"][0]')
check "approve sign-up" "$(curl -s -b "$A" -X PATCH "$BASE/admin/users/$jid" -H 'content-type: application/json' -d '{"is_active":true}' | j '(d["is_active"], d["pending"])')" "(True, False)"
check "approved account logs in" "$(login "$J" smokejoin1 joinpass123)" 200
check "session cookie lasts 60 days" "$(curl -s -o /dev/null -D - -X POST "$BASE/auth/login" -H 'content-type: application/json' -d '{"username":"smokejoin1","password":"joinpass123"}' | grep -io 'max-age=[0-9]*' | head -1)" "Max-Age=5184000"
check "only admins delete accounts" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/admin/users/$jid")" 403
check "delete account" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/admin/users/$jid")" 204
curl -s -b "$A" -o /dev/null -X PUT "$BASE/admin/signup" -H 'content-type: application/json' -d '{"mode":"open"}'
check "open sign-up signs in at once" "$(signup smokejoin2)/$(curl -s -b "$J" -o /dev/null -w '%{http_code}' "$BASE/auth/me")" "201/200"
jid=$(curl -s -b "$A" "$BASE/admin/users" | j '[u["id"] for u in d["items"] if u["username"]=="smokejoin2"][0]')
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/admin/users/$jid"
curl -s -b "$A" -o /dev/null -X PUT "$BASE/admin/signup" -H 'content-type: application/json' -d '{"mode":"off"}'

# radio (stations from radio.bsod.kr; a live check needs the internet, so only the list and errors here)
check "radio stations listed" "$(curl -s -b "$U" "$BASE/radio/stations" | j 'len(d["stations"]) > 100 and len(d["regions"]) == 9')" True
check "unknown station" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/radio/nope/stream")" 404
check "radio needs a login" "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/radio/stations")" 401
# statistics: admin only
check "statistics" "$(curl -s -b "$A" "$BASE/admin/stats" | j 'sorted(d)')" "['days', 'library', 'plays', 'storage', 'users']"
check "statistics admin only" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/admin/stats")" 403

# duplicate artists/genres and album descriptions: admin only
check "duplicate names admin only" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/admin/duplicates/artist")" 403
check "duplicate name suggestions" "$(curl -s -b "$A" "$BASE/admin/duplicates/genre" | j 'sorted(d)')" "['groups', 'merged']"
check "merge with unknown id refused" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/admin/merge/artist" -H 'content-type: application/json' -d '{"keep":2147483000,"ids":[2147483001]}')" 404
check "album description admin only" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X PUT "$BASE/admin/albums/$aid/notes" -H 'content-type: application/json' -d '{"text":"x"}')" 403
curl -s -b "$A" -o /dev/null -X PUT "$BASE/admin/albums/$aid/notes" -H 'content-type: application/json' -d '{"text":"smoke 소개\n둘째 줄"}'
check "album description saved" "$(curl -s -b "$U" "$BASE/albums/$aid" | j '(d["description"], d["description_source"])')" "('smoke 소개\n둘째 줄', 'manual')"
curl -s -b "$A" -o /dev/null -X PUT "$BASE/admin/albums/$aid/notes" -H 'content-type: application/json' -d '{"text":""}'
check "album description cleared" "$(curl -s -b "$A" "$BASE/albums/$aid" | j 'd["description"]')" None

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

# recycle bins and NAS thumbnail folders are never scanned or listed
scan >/dev/null  # a whole-library scan to compare with
before=$(curl -s -b "$A" "$BASE/admin/scan/latest" | j 'd["job"]["scanned"]')
mkdir -p "$MUSIC/#recycle"; cp "$(find "$MUSIC" -type f -name '*.mp3' | head -1)" "$MUSIC/#recycle/smoke-trash.mp3"
check "scan with a recycle bin" "$(scan)" done
check "recycle bin not indexed or listed" "$(curl -s -b "$A" "$BASE/admin/scan/latest" | j 'd["job"]["scanned"]')/$(curl -s -b "$A" "$BASE/admin/folders" | j '"#recycle" in [f["path"] for f in d["items"]]')" "$before/False"
rm -rf "$MUSIC/#recycle"

# an MP3 with junk after its tag ("can't sync to MPEG frame"): read with ffmpeg, played converted
mkdir -p "$MUSIC/smoke-damaged"
python3 - "$(find "$MUSIC" -type f -name '*.mp3' -not -path '*smoke-damaged*' | head -1)" "$MUSIC/smoke-damaged/broken.mp3" <<'PY'
import os, sys
d = open(sys.argv[1], "rb").read()
cut = 10 + sum((b & 0x7F) << (7 * (3 - i)) for i, b in enumerate(d[6:10])) if d[:3] == b"ID3" else 0
open(sys.argv[2], "wb").write(d[:cut] + bytes(3_000_000) + d[cut:])  # zeros: never mistaken for audio
PY
check "scan with a damaged MP3" "$(scan)" done
did=$(curl -s -b "$A" "$BASE/tracks?limit=500" | j '[t["id"] for t in d["items"] if t["damaged"]][0] if any(t["damaged"] for t in d["items"]) else ""')
check "damaged MP3 indexed" "$([ -n "$did" ] && echo yes)" yes
check "damaged MP3 streamed converted" "$(curl -s -b "$A" -o /dev/null -w '%{http_code} %{content_type}' "$BASE/tracks/$did/stream?quality=320&whole=1")" "200 audio/mpeg"
rm -rf "$MUSIC/smoke-damaged"
scan >/dev/null  # it goes missing now, not in the delete check below

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
