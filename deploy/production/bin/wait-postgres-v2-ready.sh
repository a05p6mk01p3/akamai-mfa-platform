#!/bin/sh
set -eu

i=0
while [ "$i" -lt 60 ]; do
    if /usr/bin/podman exec akamai-mfa-postgres-v2 \
        sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
        >/dev/null 2>&1
    then
        echo "POSTGRES_V2_READY=PASS"
        exit 0
    fi

    i=$((i + 1))
    sleep 1
done

echo "POSTGRES_V2_READY=FAIL" >&2
exit 1
