#!/bin/sh
set -eu

i=0

while [ "$i" -lt 90 ]; do
    if /usr/bin/podman exec akamai-mfa-api-v2 \
        python -c '
import urllib.request
import sys

url = "http" + "://" + "127.0.0.1:8000/ready"

try:
    with urllib.request.urlopen(url, timeout=1) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
' >/dev/null 2>&1
    then
        echo "API_V2_READY=PASS"
        exit 0
    fi

    i=$((i + 1))
    sleep 1
done

echo "API_V2_READY=FAIL" >&2
exit 1
