#!/bin/bash

set -ex

context=$(cd $(dirname $0)/.. && pwd)/flatpak-indexer/redis
exec podman build $context -t flatpak-status-redis
