#!/bin/bash

set -e

failed=false

fetch_cache=false
update_test_data=false

while [ "$#" '>' 0 ] ; do
    case "$1" in
        --update-test-data)
            update_test_data=true
            ;;
        --no-fetch-cache)
            fetch_cache=false
            ;;
    esac

    shift
done

if $update_test_data ; then
    if $fetch_cache ; then
        ./utils/update-test-data.sh --from-cache
    else
        ./utils/update-test-data.sh --no-fetch-cache
    fi
fi

set -x

pytest --cov=flatpak_status --cov-report=term-missing tests
[ $? == 0 ] || failed=true
flake8 flatpak_status utils tests
[ $? == 0 ] || failed=true
node_modules/.bin/eslint web/status.js
[ $? == 0 ] || failed=true

$failed && exit 1
