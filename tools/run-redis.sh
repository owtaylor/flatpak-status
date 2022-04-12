#!/bin/bash

set -ex

topdir=$(cd $(dirname $0)/.. && pwd)

podman run \
        --rm --user 0:0 \
        -v $topdir/cache/redis-data:/data:z \
        flatpak-status-redis \
        chown redis:redis /data

exec podman run \
        -e REDIS_PASSWORD=abc123 \
	--name=flatpak-status-redis --rm \
        -p 127.0.0.1:16379:6379 \
        -v $topdir/cache/redis-data:/data:z \
        flatpak-status-redis
