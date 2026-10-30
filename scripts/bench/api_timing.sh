#!/bin/bash
# Times the main API calls (median of 5) against a running instance.
# Usage: scripts/bench/api_timing.sh <base-url> <admin-user> <admin-password>
# The first request after a library change builds the cache; the median shows the cached time.
set -u
B="${1:?base url}/api/v1"
J=$(mktemp); trap 'rm -f "$J"' EXIT
curl -s -c "$J" -H 'Content-Type: application/json' -d "{\"username\":\"$2\",\"password\":\"$3\"}" "$B/auth/login" -o /dev/null
t() {
  local v=$(for i in 1 2 3 4 5; do curl -s -b "$J" -o /dev/null -w '%{time_total}\n' "$B$1"; done | sort -n | sed -n 3p)
  printf '%-48s %6.0f ms\n' "$1" "$(echo "$v*1000" | bc)"
}
for p in "/tracks?limit=200" "/tracks?sort=artist&limit=200" "/tracks?q=%EB%B3%84%EB%B9%9B&limit=100" "/tracks?q=zzz&limit=100" \
  "/albums?limit=120" "/albums?sort=title&limit=120" "/albums?q=%EB%B0%94%EB%8B%A4&limit=120" "/artists?limit=500" "/genres" \
  "/collections/home" "/charts?kind=chart&limit=120" "/charts/1" "/albums/1" "/artists/1" "/albums/1/cover?size=thumb"; do t "$p"; done
