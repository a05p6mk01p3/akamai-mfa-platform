#!/bin/sh
set -eu

i=0
while [ "$i" -lt 90 ]; do
    if /usr/bin/podman exec akamai-mfa-mcp-v2 \
        python -c '
import socket
s = socket.create_connection(("127.0.0.1", 9000), timeout=1)
s.close()
' >/dev/null 2>&1
    then
        echo "MCP_V2_READY=PASS"
        exit 0
    fi

    i=$((i + 1))
    sleep 1
done

echo "MCP_V2_READY=FAIL" >&2
exit 1
