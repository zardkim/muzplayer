#!/bin/bash
# Build the muzplayer image and push it to Harbor.
# Usage: ./build.sh 0.1.0      (also tags latest)
set -e
export DOCKER_CONFIG="$HOME/.docker-harbor/muzplayer"

REGISTRY="harbor.nurilab.pe.kr"
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

echo "Done: $REGISTRY/$IMAGE:$VERSION"
