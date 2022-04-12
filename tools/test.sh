#!/bin/bash

set -e

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
        ./tools/update-test-data.sh --from-cache
    else
        ./tools/update-test-data.sh --no-fetch-cache
    fi
fi

failed=""

set +e -x

pytest --cov=flatpak_status --cov-report=term-missing tests
[ $? == 0 ] || failed="$failed pytest"
flake8 flatpak_status tools tests
[ $? == 0 ] || failed="$failed flake8"
node_modules/.bin/eslint web/status.js
[ $? == 0 ] || failed="$failed eslint"

set -e +x

if [ "$failed" != "" ] ; then
    echo "FAILED:$failed"
    exit 1
fi
