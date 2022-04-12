#!/bin/bash

set -e

find . -name __pycache__ -exec rm -rf '{}' ';' -prune

podman build -t flatpak-status:latest .
./tools/update-test-data.sh --only-fetch-cache
podman run \
       --rm \
       -v $(pwd)/cache:/opt/flatpak-status/cache:z \
       -v $(pwd)/.test-data:/opt/flatpak-status/.test-data:z \
       -v $(pwd)/test-data:/opt/flatpak-status/test-data:z \
       flatpak-status:latest \
       pipenv run ./tools/test.sh --update-test-data --no-fetch-cache
