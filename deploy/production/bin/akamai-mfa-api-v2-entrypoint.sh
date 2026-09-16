#!/bin/sh
set -eu

required_secret() {
    file="$1"
    var="$2"

    if [ ! -r "$file" ]; then
        echo "required secret file unavailable: $file" >&2
        exit 1
    fi

    value="$(cat "$file")"

    if [ -z "$value" ]; then
        echo "required secret file is empty: $file" >&2
        exit 1
    fi

    export "$var=$value"
}

optional_secret() {
    file="$1"
    var="$2"

    if [ -r "$file" ]; then
        value="$(cat "$file")"
        if [ -n "$value" ]; then
            export "$var=$value"
        fi
    fi
}

required_secret /run/secrets/akamai_client_token AKAMAI_CLIENT_TOKEN
required_secret /run/secrets/akamai_client_secret AKAMAI_CLIENT_SECRET
required_secret /run/secrets/akamai_access_token AKAMAI_ACCESS_TOKEN
required_secret /run/secrets/database_url DATABASE_URL

optional_secret /run/secrets/http_proxy HTTP_PROXY
optional_secret /run/secrets/https_proxy HTTPS_PROXY

i=0
while [ "$i" -lt 60 ]; do
    if python -c 'from app.api.v2.dependencies import database; raise SystemExit(0 if database().ping() else 1)' >/dev/null 2>&1; then
        echo "DATABASE_READY=PASS"
        break
    fi

    i=$((i + 1))

    if [ "$i" -ge 60 ]; then
        echo "DATABASE_READY=FAIL" >&2
        exit 1
    fi

    sleep 1
done

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2 \
    --proxy-headers
