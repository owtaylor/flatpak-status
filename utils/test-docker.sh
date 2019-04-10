#!/bin/bash

set -e

find . -name __pycache__ -exec rm -rf '{}' ';' -prune

docker build --no-cache -t flatpak-status:latest .
./utils/update-test-data.sh --only-fetch-cache
docker run \
       --rm \
       -v $(pwd)/cache:/opt/flatpak-status/cache \
       -v $(pwd)/.test-data:/opt/flatpak-status/.test-data \
       -v $(pwd)/test-data:/opt/flatpak-status/test-data \
       flatpak-status:latest \
       pipenv run ./utils/test.sh --update-test-data --no-fetch-cache
