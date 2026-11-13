#!/bin/bash
# The maintainer's build: the image pushed to his own Harbor registry (the public image on Docker Hub
# is built by GitHub Actions, .github/workflows/docker-publish.yml).
# Usage: ./build.sh 0.1.0      (also tags latest); REGISTRY=... for another registry
set -e
export DOCKER_CONFIG="${DOCKER_CONFIG:-$HOME/.docker-harbor/muzplayer}"

REGISTRY="${REGISTRY:-harbor.nurilab.pe.kr}"
IMAGE="muzplayer/muzplayer"
VERSION="${1:?usage: ./build.sh <version>}"

cd "$(dirname "$0")"

echo "Building $REGISTRY/$IMAGE:$VERSION ..."
docker build --build-arg APP_VERSION="$VERSION" \
  -t "$REGISTRY/$IMAGE:$VERSION" \
  -t "$REGISTRY/$IMAGE:latest" \
  .

echo "Pushing ..."
docker push "$REGISTRY/$IMAGE:$VERSION"
docker push "$REGISTRY/$IMAGE:latest"

# Harbor keeps the 4 most recently pushed images (the project's tag retention policy, also run
# daily at 04:00 UTC); run it now so an older one goes as soon as a new one is in.
# Local endpoint (same server); the robot's login is read from DOCKER_CONFIG, never printed.
HARBOR_API="http://localhost:8992/api/v2.0"
AUTH=$(python3 -c "import json,os; print(json.load(open(os.path.join(os.environ['DOCKER_CONFIG'], 'config.json')))['auths']['$REGISTRY']['auth'])" 2>/dev/null || true)
RETENTION=$(curl -s -H "Authorization: Basic $AUTH" "$HARBOR_API/projects/${IMAGE%%/*}" | python3 -c "import json,sys; print(json.load(sys.stdin)['metadata'].get('retention_id', ''))" 2>/dev/null || true)
if [ -n "$RETENTION" ]; then
  curl -s -o /dev/null -w "Retention run (keep 4): %{http_code}\n" -X POST -H "Authorization: Basic $AUTH" \
    -H 'Content-Type: application/json' -d '{"dry_run":false}' "$HARBOR_API/retentions/$RETENTION/executions" || true
else
  echo "Retention: no policy found (skipped)"
fi

echo "Done: $REGISTRY/$IMAGE:$VERSION"
