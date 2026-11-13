#!/bin/sh
set -e
cd /app

# Started as root: make the data and settings folders writable, then drop to PUID:PGID.
if [ "$(id -u)" = "0" ]; then
  PUID="${PUID:-1000}"
  PGID="${PGID:-1000}"
  mkdir -p /data /conf
  # only what isn't owned right (the cover cache can hold tens of thousands of files)
  find /data /conf \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown -h "$PUID:$PGID" {} +
  # the extraction folder (extract.py), when it is mounted writable (Docker makes a missing one as root)
  EXTRACT="${EXTRACT_DIR:-$(dirname "${MUSIC_DIR:-/library/music}")/cover music}"
  if [ -d "$EXTRACT" ] && [ -w "$EXTRACT" ]; then
    find "$EXTRACT" \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown -h "$PUID:$PGID" {} +
  fi
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$0" "$@"
fi

python -m app.migrate
python -m app.bootstrap
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips='*'
