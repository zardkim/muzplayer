#!/bin/bash
# API smoke test against a running instance.
# Usage: scripts/smoke_test.sh <base-url> <admin-user> <admin-password> <music-dir-on-host>
# On a fresh install the admin is made here first (the first account is the admin).
# Use a TEST library only: it temporarily moves one .mp3 out of the music folder and
# leaves a disabled user named "smokeuser".
set -u
BASE="${1:?base url}/api/v1"; ADMIN="$2"; ADMIN_PW="$3"; MUSIC="$4"
TMP=$(mktemp -d)
MOVED=""; MOVED_DIR=""
cleanup() {
  [ -n "$MOVED" ] && [ -f "$TMP/moved.mp3" ] && mv "$TMP/moved.mp3" "$MOVED"
  [ -n "$MOVED_DIR" ] && mv "$MOVED_TO/$(basename "$MOVED_DIR")" "$MOVED_DIR" && rmdir "$MOVED_TO"
  rm -rf "$TMP"
}
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
# an admin's lyrics for the song (api/lyrics_admin.py): ahead of its own, shifted, then back to automatic
check "lyrics admin reads the song" "$(curl -s -b "$A" "$BASE/admin/lyrics/$fid" | j '"shown" in d')" True
curl -s -b "$A" -o /dev/null -X PUT "$BASE/admin/lyrics/$fid" -H 'content-type: application/json' -d '{"lrc":"[00:01.00]smoke line\n[00:04.00]smoke two","source":"manual","offset_ms":500}'
check "chosen lyrics shown, shifted" "$(curl -s -b "$A" "$BASE/tracks/$fid/lyrics?v=1" | j 'd["synced"][0]')" "[1.5, 'smoke line']"
check "lyrics back to automatic" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/admin/lyrics/$fid")" 204
check "search box suggests words" "$(curl -s -b "$A" "$BASE/search/suggest?q=a" | j 'sorted(d)')" "['items']"
check "songs say whether they have lyrics" "$(curl -s -b "$A" "$BASE/tracks?limit=1" | j '"has_lyrics" in d["items"][0]')" True
curl -s -b "$A" -o /dev/null -X PUT "$BASE/favorites/$tid"
check "favorites list" "$(curl -s -b "$A" "$BASE/favorites" | j '[t["id"] for t in d["items"]].count('"$tid"')')" 1
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/favorites/$tid"
check "charts list" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/charts")" 200
check "charts & themes page" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/collections/home")" 200
# stations (home): each gives songs, leaving out those already queued; one needing a seed asks for it
check "library radio station" "$(curl -s -b "$A" "$BASE/stations/library?limit=5" | j 'len(d["tracks"])')" 5
first=$(curl -s -b "$A" "$BASE/stations/library?limit=5" | j '",".join(str(t["id"]) for t in d["tracks"])')
check "station leaves out queued songs" "$(curl -s -b "$A" "$BASE/stations/library?limit=50&exclude=$first" | j "len(set(str(t['id']) for t in d['tracks']) & set('$first'.split(',')))")" 0
check "random album station plays one album" "$(curl -s -b "$A" "$BASE/stations/randomalbum" | j 'len(set(t["album_id"] for t in d["tracks"])) <= 1')" True
check "artist mix needs an artist" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/stations/artist")" 400
check "no such station" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/stations/nope")" 404
check "folder kinds list" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/admin/folders")" 200
# one folder: rescan reads every file again and keeps the songs (ids); reset is announced with what it takes
top=$(curl -s -b "$A" "$BASE/admin/folders" | j '[f["path"] for f in d["items"] if f["track_count"]][0]')
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
check "scan problems list" "$(curl -s -b "$A" "$BASE/admin/scan/issues" | j '"items" in d and "total" in d')" True
check "scan problems are admin-only" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/admin/scan/issues")" 403
# a shared playlist made from a chart: everyone plays it, only its maker (or an admin) changes it
cid=$(curl -s -b "$A" "$BASE/charts" | j 'd["items"][0]["id"] if d["items"] else ""')
if [ -n "$cid" ]; then
  check "only an admin makes a shared playlist" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X POST "$BASE/charts/$cid/shared-playlist" -H 'content-type: application/json' -d '{}')" 403
  spid=$(curl -s -b "$A" -X POST "$BASE/charts/$cid/shared-playlist" -H 'content-type: application/json' -d '{}' | j 'd["id"]')
  check "shared playlist listed for everyone" "$(curl -s -b "$U" "$BASE/playlists/shared" | j "[p['id'] for p in d['items']].count($spid)")" 1
  check "another user plays it, can't change it" "$(curl -s -b "$U" "$BASE/playlists/$spid" | j 'd["can_edit"]')/$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/playlists/$spid")" "False/404"
  check "not among the maker's own playlists" "$(curl -s -b "$A" "$BASE/playlists" | j "[p['id'] for p in d['items']].count($spid)")" 0
  check "the chart knows its shared playlist" "$(curl -s -b "$A" "$BASE/charts/$cid" | j 'd["shared_playlist_id"]')" "$spid"
  check "shared playlist deleted" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/playlists/$spid")" 204
fi
pid=$(curl -s -b "$A" -X POST "$BASE/playlists" -H 'content-type: application/json' -d '{"name":"smoke"}' | j 'd["id"]')
curl -s -b "$A" -o /dev/null -X POST "$BASE/playlists/$pid/tracks" -H 'content-type: application/json' -d "{\"track_ids\":[$tid]}"
check "a song already in a playlist isn't added twice" "$(curl -s -b "$A" -X POST "$BASE/playlists/$pid/tracks" -H 'content-type: application/json' -d "{\"track_ids\":[$tid]}" | j '[d["added"], d["skipped"]]')" "[0, 1]"
# songs moved into another playlist of mine (they leave this one), and not into the same one
pid2=$(curl -s -b "$A" -X POST "$BASE/playlists" -H 'content-type: application/json' -d '{"name":"smoke 2"}' | j 'd["id"]')
check "songs moved into another playlist" "$(curl -s -b "$A" -X POST "$BASE/playlists/$pid/transfer" -H 'content-type: application/json' -d "{\"target_id\":$pid2,\"mode\":\"move\"}" | j '[d["added"], d["removed"]]')" "[1, 1]"
check "moved: gone from the first, in the second" "$(curl -s -b "$A" "$BASE/playlists/$pid" | j 'len(d["entries"])')/$(curl -s -b "$A" "$BASE/playlists/$pid2" | j 'len(d["entries"])')" "0/1"
check "not into the same playlist" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/playlists/$pid2/transfer" -H 'content-type: application/json' -d "{\"target_id\":$pid2}")" 400
check "not into someone else's playlist" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X POST "$BASE/playlists/$pid2/transfer" -H 'content-type: application/json' -d "{\"target_id\":$pid}")" 404
curl -s -b "$A" -o /dev/null -X POST "$BASE/playlists/$pid2/transfer" -H 'content-type: application/json' -d "{\"target_id\":$pid,\"mode\":\"move\"}"
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/playlists/$pid2"
check "a playlist name of spaces is refused" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X PATCH "$BASE/playlists/$pid" -H 'content-type: application/json' -d '{"name":"   "}')" 422
check "other user's playlist is 404" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/playlists/$pid")" 404
check "other user's playlists don't show mine" "$(curl -s -b "$U" "$BASE/playlists" | j "$pid in [p['id'] for p in d['items']]")" False
check "settings are kept with the account" "$(curl -s -b "$U" -X PATCH "$BASE/auth/me" -H 'content-type: application/json' -d '{"prefs":{"v":1,"t":1,"theme":"spotify"}}' >/dev/null; curl -s -b "$U" "$BASE/auth/me" | j 'd["prefs"]["theme"]')" spotify
check "everyone has a default playlist" "$(curl -s -b "$U" "$BASE/playlists" | j '[p["is_default"] for p in d["items"]]')" "[True]"
dpl=$(curl -s -b "$U" "$BASE/playlists" | j 'd["items"][0]["id"]')
check "the default playlist can't be deleted" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/playlists/$dpl")" 400
check "everyone has a default video playlist" "$(curl -s -b "$U" "$BASE/video-playlists" | j '[p["is_default"] for p in d["items"]]')" "[True]"

# signing out ends the session on the server too
D="$TMP/device.txt"; login "$D" smokeuser smokepass1 >/dev/null; cp "$D" "$TMP/device-old.txt"
check "logout" "$(curl -s -b "$D" -c "$D" -o /dev/null -w '%{http_code}' -X POST "$BASE/auth/logout")" 204
check "signed out session is gone" "$(curl -s -b "$TMP/device-old.txt" -o /dev/null -w '%{http_code}' "$BASE/auth/me")" 401
check "other sessions stay" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/auth/me")" 200

# stars, likes, play counts, mixes and smart playlists are each user's own
aid=$(curl -s -b "$A" "$BASE/tracks?sort=title" | j 'next(x["album_id"] for x in d["items"] if x["album_id"] and x["album_kind"] != "chart")')  # an album (not a chart's or theme's)
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
check "album shows its folder" "$(curl -s -b "$A" "$BASE/albums/$aid" | j 'len(d["folders"]) > 0 and all("/" in f for f in d["folders"])')" True
check "song info: file, encoding, tags" "$(curl -s -b "$A" "$BASE/tracks/$tid/info" | j '(d["file"] != "", d["size"] > 0, "sample_rate" in d["stream"], isinstance(d["tags"], dict))')" "(True, True, True, True)"
afolder=$(curl -s -b "$A" "$BASE/albums/$aid" | j 'd["folders"][0]')
check "an album's metadata refreshed (its folder only)" "$(scan "$(python3 -c 'import json,sys; print(json.dumps({"folder": sys.argv[1], "mode": "rescan"}))' "$afolder")")/$(curl -s -b "$A" "$BASE/admin/scan/latest" | j 'd["job"]["folder"] == '"$(python3 -c 'import json,sys,unicodedata; print(json.dumps(unicodedata.normalize("NFC", sys.argv[1])))' "$afolder")")" "done/True"
check "no folder outside the library" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/admin/scan" -H 'content-type: application/json' -d '{"folder":"album/../x","mode":"rescan"}')" 400
check "no reset of a folder inside one" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/admin/scan" -H 'content-type: application/json' -d '{"folder":"album/x","mode":"reset"}')" 400
check "no info of a song that isn't there" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/tracks/999999/info")" 404
check "smart playlist follows its rules" "$(curl -s -b "$A" "$BASE/playlists/$sid" | j "$tid in [e['track']['id'] for e in d['entries']]")" True
check "songs can't be put in a smart playlist" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/playlists/$sid/tracks" -H 'content-type: application/json' -d "{\"track_ids\":[$tid]}")" 400
# the smart playlist wizard: each user's taste, lists made from it, kept for a day, songs left out
curl -s -b "$U" -o /dev/null -X PUT "$BASE/taste" -H 'content-type: application/json' -d '{}'
check "taste saved" "$(curl -s -b "$A" -X PUT "$BASE/taste" -H 'content-type: application/json' -d '{"decades":[2010,2020],"skip_recent_days":0}' | j 'd["taste"]["decades"]')" "[2010, 2020]"
check "other user's taste separate" "$(curl -s -b "$U" "$BASE/taste" | j 'd["taste"]["decades"]')" "[]"
check "unknown decade refused" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X PUT "$BASE/taste" -H 'content-type: application/json' -d '{"decades":[1940]}')" 422
check "wizard suggestions" "$(curl -s -b "$A" "$BASE/taste/suggest" | j 'sorted(d)')" "['artists', 'genres']"
check "wizard preview counts" "$(curl -s -b "$A" -X POST "$BASE/smart/preview" -H 'content-type: application/json' -d '{"rules":{"profile":true,"limit":5},"taste":{}}' | j 'd["matching"] > 0 and 0 < d["count"] <= 5')" True
check "preview: one song per artist" "$(curl -s -b "$A" -X POST "$BASE/smart/preview" -H 'content-type: application/json' -d '{"rules":{"profile":true,"limit":8,"per_artist":1},"taste":{}}' | j '(lambda a: len(set(a)) == len(a) > 0)([t["artist_id"] for t in d["tracks"] if t["artist_id"]])')" True
check "preview: familiar and new mixed" "$(curl -s -b "$A" -X POST "$BASE/smart/preview" -H 'content-type: application/json' -d '{"rules":{"profile":true,"limit":10,"mix":"familiar"},"taste":{}}' | j 'd["count"] > 0')" True
wid=$(curl -s -b "$A" -X POST "$BASE/playlists" -H 'content-type: application/json' -d '{"name":"smoke wizard","rules":{"profile":true,"limit":5,"refresh":"daily"}}' | j 'd["id"]')
w1=$(curl -s -b "$A" "$BASE/playlists/$wid" | j '([e["track"]["id"] for e in d["entries"]], d["made_at"])')
check "kept for a day: same songs when opened again" "$(curl -s -b "$A" "$BASE/playlists/$wid" | j '([e["track"]["id"] for e in d["entries"]], d["made_at"])')" "$w1"
curl -s -b "$A" -o /dev/null -X POST "$BASE/playlists/$wid/refresh"
check "picked again after refresh" "$([ "$(curl -s -b "$A" "$BASE/playlists/$wid" | j '([e["track"]["id"] for e in d["entries"]], d["made_at"])')" != "$w1" ] && echo picked)" picked
check "taste applies (decades)" "$(curl -s -b "$A" "$BASE/playlists/$wid" | j 'len(d["entries"]) > 0 and all((e["track"]["year"] or 0) >= 2010 for e in d["entries"])')" True
wt=$(curl -s -b "$A" "$BASE/playlists/$wid" | j 'd["entries"][0]["track"]["id"]')
w2=$(curl -s -b "$A" "$BASE/playlists/$wid" | j '([e["track"]["id"] for e in d["entries"] if e["track"]["id"] != '"$wt"'], d["made_at"])')
check "song left out of my smart playlists" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/taste/exclude/$wt")/$(curl -s -b "$A" "$BASE/playlists/$wid" | j "$wt in [e['track']['id'] for e in d['entries']]")" "204/False"
check "the rest of a kept list stays" "$(curl -s -b "$A" "$BASE/playlists/$wid" | j '([e["track"]["id"] for e in d["entries"]], d["made_at"])')" "$w2"
check "left-out song listed, then back" "$(curl -s -b "$A" "$BASE/taste" | j "[t['id'] for t in d['tracks']]")/$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/taste/exclude/$wt")/$(curl -s -b "$A" "$BASE/taste" | j 'd["tracks"]')" "[$wt]/204/[]"
check "other user can't open my smart playlist" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/playlists/$wid")" 404
check "rules-only smart playlist unchanged" "$(curl -s -b "$A" "$BASE/playlists/$sid" | j '(d["made_at"], '"$tid"' in [e["track"]["id"] for e in d["entries"]])')" "(None, True)"
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/playlists/$wid"
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
check "no linking a video that isn't there" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/videos/999999/link" -H 'content-type: application/json' -d '{"auto":true}')" 404
check "liking a video that isn't there" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X PUT "$BASE/videos/999999/favorite")" 404
vfile=$(curl -s -b "$A" "$BASE/videos?limit=200" | j 'next((v["id"] for v in d["items"] if v["file_path"]), "")')
[ -n "$vfile" ] && check "video info: path and codec" "$(curl -s -b "$U" "$BASE/videos/$vfile/info" | j '(d["file"] != "", d["exists"], len(d.get("probe", {}).get("streams", [])) > 0)')" "(True, True, True)"
check "no info of a video that isn't there" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/videos/999999/info")" 404
check "no similar videos of a video that isn't there" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/videos/999999/related")" 404
# music video kinds: everyone sees them, an admin adds, renames, orders and removes them ("other" stays)
check "video kinds listed, other last" "$(curl -s -b "$U" "$BASE/video-kinds" | j '[k["key"] for k in d][-1]')" other
check "only an admin adds a video kind" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X POST "$BASE/video-kinds" -H 'content-type: application/json' -d '{"name":"x"}')" 403
vk=$(curl -s -b "$A" -X POST "$BASE/video-kinds" -H 'content-type: application/json' -d '{"name":"smoke kind"}' | j 'd["key"]')
check "video kind added before other" "$(curl -s -b "$A" "$BASE/video-kinds" | j '[k["key"] for k in d][-2:]')" "['$vk', 'other']"
check "video kind renamed" "$(curl -s -b "$A" -X PATCH "$BASE/video-kinds/$vk" -H 'content-type: application/json' -d '{"name":"smoke kind 2"}' | j 'd["name"]')" "smoke kind 2"
check "no video of a kind that isn't there" "$(curl -s -b "$A" -X POST "$BASE/videos" -H 'content-type: application/json' -d "{\"video\":\"dQw4w9WgXcQ\",\"kind\":\"nosuchkind\",\"album_id\":$aid}" | j 'd["detail"]')" video_kind_unknown
check "the other kind stays" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/video-kinds/other")" 400
check "video kind removed" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/video-kinds/$vk")" 204
# a song taken out of a NAS video (extract.py; no internet): into the library as "extracted", then deleted
export XPATH="연결테스트/Banana Pancakes.mp4"
xvid=$(curl -s -b "$A" "$BASE/videos/files" | python3 -c 'import json,os,sys; d=json.load(sys.stdin); print(next((f["video_id"] or "" for f in d["items"] if f["path"] == os.environ["XPATH"]), "none"))')
xmade=""
if [ "$xvid" = "" ]; then
  xvid=$(curl -s -b "$A" -X POST "$BASE/videos/files" -H 'content-type: application/json' -d "{\"path\":\"$XPATH\",\"kind\":\"mv\",\"title\":\"Banana Pancakes\"}" | j 'd["id"]'); xmade=1
fi
check "extraction folder ready" "$(curl -s -b "$A" "$BASE/extract/status" | j 'd["folder_ok"]')" True
check "only an admin extracts" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' -X POST "$BASE/videos/$xvid/extract" -H 'content-type: application/json' -d '{}')" 403
if [ "$xvid" != none ]; then
  xjob=$(curl -s -b "$A" -X POST "$BASE/videos/$xvid/extract" -H 'content-type: application/json' -d '{"format":"m4a"}' | j 'd["id"]')
  for _ in $(seq 1 90); do
    xst=$(curl -s -b "$A" "$BASE/extract/jobs" | j "next(x['status'] for x in d['items'] if x['id'] == $xjob)"); [ "$xst" = done ] || [ "$xst" = failed ] && break; sleep 1
  done
  check "audio extracted from a NAS video" "$xst" done
  xalbum=$(curl -s -b "$A" "$BASE/extract/jobs" | j "next(x['album_id'] for x in d['items'] if x['id'] == $xjob)")
  check "extracted song listed as extracted" "$(curl -s -b "$A" "$BASE/albums/$xalbum" | j 'd["kind"]')" extracted
  xtrack=$(curl -s -b "$A" "$BASE/extract/jobs" | j "next(x['track_id'] for x in d['items'] if x['id'] == $xjob)")
  check "extracted song on the covers page" "$(curl -s -b "$A" "$BASE/tracks?kind=extracted&limit=500" | j "any(x['id'] == $xtrack for x in d['items'])")" True
  check "extracted song's tags read" "$(curl -s -b "$A" "$BASE/extract/tracks/$xtrack" | j 'd["format"]')" m4a
  xedit=$(curl -s -b "$A" -X PUT "$BASE/extract/tracks/$xtrack" -H 'content-type: application/json' -d '{"title":"Smoke Edited","artist":"Smoke Singer","track":3}')
  check "tag edit keeps the song" "$(echo "$xedit" | j 'd["track_id"]')" "$xtrack"
  check "tag edit renames the file" "$(echo "$xedit" | j 'd["file_path"].split("/", 1)[1]')" "Smoke Singer/1-03 Smoke Edited.m4a"
  check "a library song's tags not editable" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/extract/tracks/$(curl -s -b "$A" "$BASE/tracks?limit=1" | j 'd["items"][0]["id"]')")" 400
  check "extracted song deleted" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/extract/jobs/$xjob?file=true")" 204
  for _ in $(seq 1 30); do [ "$(curl -s -b "$A" "$BASE/admin/scan/latest" | j 'd["job"]["status"]')" = running ] || break; sleep 1; done
  # linked to an album instead of its song (then back as it was)
  xwas=$(curl -s -b "$A" "$BASE/videos?q=Banana%20Pancakes&limit=200" | j "next((x['track_id'] for x in d['items'] if x['id'] == $xvid), None)")
  link() { curl -s -b "$1" -o /dev/null -w '%{http_code}' -X POST "$BASE/videos/$xvid/link" -H 'content-type: application/json' -d "$2"; }
  check "video linked to an album" "$(curl -s -b "$A" -X POST "$BASE/videos/$xvid/link" -H 'content-type: application/json' -d "{\"album_id\":$aid}" | j '[d["album_id"], d["track_id"], d["target"]["type"]]')" "[$aid, None, 'album']"
  check "album's videos listed" "$(curl -s -b "$A" "$BASE/videos?album_id=$aid&limit=200" | j "any(x['id'] == $xvid for x in d['items']) and all(x['album_id'] == $aid for x in d['items'])")" True
  check "song and album not both" "$(link "$A" "{\"album_id\":$aid,\"track_id\":1}")" 422
  check "no linking to a missing album" "$(link "$A" '{"album_id":999999}')" 404
  check "only an admin links videos" "$(link "$U" "{\"album_id\":$aid}")" 403
  if [ "$xwas" = None ]; then link "$A" '{}' > /dev/null; else link "$A" "{\"track_id\":$xwas}" > /dev/null; fi
  [ -n "$xmade" ] && curl -s -b "$A" -o /dev/null -X DELETE "$BASE/videos/$xvid"
fi
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
check "statistics" "$(curl -s -b "$A" "$BASE/admin/stats" | j 'sorted(d)')" "['books', 'days', 'library', 'plays', 'storage', 'users', 'videos']"
check "statistics admin only" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/admin/stats")" 403

# duplicate artists/genres and album descriptions: admin only
check "duplicate names admin only" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/admin/duplicates/artist")" 403
check "duplicate name suggestions" "$(curl -s -b "$A" "$BASE/admin/duplicates/genre" | j 'sorted(d)')" "['groups', 'merged', 'not_same']"
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

# a moved folder: its songs keep their rows (ids, likes, playlists) at the new path, also moved back
mdir=$(dirname "$(find "$MUSIC" -mindepth 3 -type f -name '*.mp3' -not -path '*/chart*' | head -1)")
mtop=${mdir#"$MUSIC"/}; mtop=${mtop%%/*}  # its top-level folder
ids_before=$(curl -s -b "$A" "$BASE/tracks?limit=500" | j 'sorted(t["id"] for t in d["items"])')
MOVED_TO="$MUSIC/$mtop/smoke-moved"; mkdir -p "$MOVED_TO"; mv "$mdir" "$MOVED_TO/"
MOVED_DIR="$mdir"
check "scan after a folder move" "$(scan "{\"folder\":\"$mtop\"}")" done
check "moved songs followed, none missing" "$(curl -s -b "$A" "$BASE/admin/scan/latest" | j '(d["job"]["moved"] > 0, d["job"]["missing"], d["job"]["added"])')" "(True, 0, 0)"
check "moved songs keep their ids" "$(curl -s -b "$A" "$BASE/tracks?limit=500" | j 'sorted(t["id"] for t in d["items"])')" "$ids_before"
mv "$MOVED_TO/$(basename "$mdir")" "$mdir"; rmdir "$MOVED_TO"; MOVED_DIR=""
check "moved back: followed again" "$(scan >/dev/null; curl -s -b "$A" "$BASE/admin/scan/latest" | j '(d["job"]["moved"] > 0, d["job"]["missing"], d["job"]["added"])')" "(True, 0, 0)"

# backup (not restored here: that would sign this test out): made, listed, a whole file, deleted
bname=$(curl -s -b "$A" -X POST "$BASE/admin/backups" | j 'd["name"]')
check "backup made" "$(curl -s -b "$A" "$BASE/admin/backups" | j "any(b['name'] == '$bname' for b in d['items'])")" True
curl -s -b "$A" -o "$TMP/backup.tgz" "$BASE/admin/backups/$bname"
check "backup holds the database" "$(tar xzf "$TMP/backup.tgz" -O manifest.json | j 'any(t["name"] == "tracks" and t["rows"] > 0 for t in d["tables"]) and "sessions" not in [t["name"] for t in d["tables"]]')" True
check "bad backup refused" "$(head -c 2000 "$TMP/backup.tgz" | curl -s -b "$A" -o /dev/null -w '%{http_code}' -X POST "$BASE/admin/restore" -H 'content-type: application/octet-stream' --data-binary @-)" 400
check "backup deleted" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' -X DELETE "$BASE/admin/backups/$bname")" 204

# backup and restore, round trip: what changed after the backup is undone (everyone signs in again),
# the newer data along (a taste, a smart playlist kept for a day, a music video kind)
curl -s -b "$A" -o /dev/null -X PUT "$BASE/taste" -H 'content-type: application/json' -d '{"decades":[1980]}'
rpid=$(curl -s -b "$A" -X POST "$BASE/playlists" -H 'content-type: application/json' -d '{"name":"smoke restore","rules":{"profile":true,"limit":3,"refresh":"daily"}}' | j 'd["id"]')
curl -s -b "$A" -o /dev/null "$BASE/playlists/$rpid"  # (its songs kept for a day)
rkind=$(curl -s -b "$A" -X POST "$BASE/video-kinds" -H 'content-type: application/json' -d '{"name":"smoke restore kind"}' | j 'd["key"]')
rname=$(curl -s -b "$A" -X POST "$BASE/admin/backups" | j 'd["name"]')
curl -s -b "$A" -o /dev/null -X PUT "$BASE/taste" -H 'content-type: application/json' -d '{"decades":[1990]}'
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/video-kinds/$rkind"
check "restore started" "$(curl -s -b "$A" -X POST "$BASE/admin/backups/$rname/restore" | j 'd["state"]')" running
for _ in $(seq 1 120); do [ "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/admin/restore")" = 200 ] && [ "$(curl -s -b "$A" "$BASE/admin/restore" | j 'd["state"]')" = running ] || break; sleep 1; done
check "signed out by the restore" "$(curl -s -b "$A" -o /dev/null -w '%{http_code}' "$BASE/auth/me")" 401
login "$A" "$ADMIN" "$ADMIN_PW" >/dev/null
check "restore done" "$(curl -s -b "$A" "$BASE/admin/restore" | j 'd["state"]')" done
check "restored: taste as backed up" "$(curl -s -b "$A" "$BASE/taste" | j 'd["taste"]["decades"]')" "[1980]"
check "restored: smart playlist and its kept songs" "$(curl -s -b "$A" "$BASE/playlists/$rpid" | j '(d["rules"]["refresh"], d["made_at"] is not None)')" "('daily', True)"
check "restored: music video kind" "$(curl -s -b "$A" "$BASE/video-kinds" | j "'$rkind' in [k['key'] for k in d]")" True
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/video-kinds/$rkind"
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/playlists/$rpid"
curl -s -b "$A" -o /dev/null -X PUT "$BASE/taste" -H 'content-type: application/json' -d '{}'
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/admin/backups/$rname"
for _ in $(seq 1 60); do [ "$(curl -s -b "$A" "$BASE/admin/scan/latest" | j 'd["job"]["status"]')" = running ] || break; sleep 1; done  # (covers made again after it)

# cleanup
curl -s -b "$A" -o /dev/null -X DELETE "$BASE/playlists/$pid"
curl -s -b "$A" -o /dev/null -X PATCH "$BASE/admin/users/$uid" -H 'content-type: application/json' -d '{"is_active":false}'
check "disabled user session revoked" "$(curl -s -b "$U" -o /dev/null -w '%{http_code}' "$BASE/auth/me")" 401
exit $fail
