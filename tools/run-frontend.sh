#!/bin/bash

set -ex

web_dir=$(cd $(dirname $0)/.. && pwd)/web
generated_dir=$(cd $(dirname $0)/.. && pwd)/generated

# Dance here is to avoid SIGWINCH being through passed to apache,
# since that is used to make apache gracefully setdown.

setsid podman run \
       --name=flatpak-indexer-frontend --rm \
       -e SERVER_NAME=flatpaks.local.fishsoup.net \
       -p 8080:80 \
       -v $web_dir:/var/www/flatpak-status/web:ro,z \
       -v $generated_dir:/var/www/flatpak-status/generated:ro,z \
       flatpak-status-frontend &
PODMAN_PID=$!

int_podman() {
    kill -INT $PODMAN_PID
}

trap int_podman SIGINT

wait $PODMAN_PID
