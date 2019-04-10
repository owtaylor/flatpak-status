#!/bin/bash

set -e

layers=--layers

while [ "$#" '>' 0 ] ; do
    case "$1" in
        --no-layers)
            layers=""
            ;;
    esac

    shift
done

find . -name __pycache__ -exec rm -rf '{}' ';' -prune

buildah bud $layers -t flatpak-status:latest .
./utils/update-test-data.sh --only-fetch-cache
podman run \
       --rm \
       -v $(pwd)/cache:/opt/flatpak-status/cache:z \
       -v $(pwd)/.test-data:/opt/flatpak-status/.test-data:z \
       -v $(pwd)/test-data:/opt/flatpak-status/test-data:z \
       flatpak-status:latest \
       pipenv run ./utils/test.sh --update-test-data --no-fetch-cache
