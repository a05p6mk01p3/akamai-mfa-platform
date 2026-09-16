#!/bin/sh
set -eu

fail() {
    echo "SMOKE=FAIL reason=$1" >&2
    exit 1
}

[ "$(id -u)" -eq 0 ] || fail root_required

for unit in \
    akamai-mfa-postgres-v2.service \
    akamai-mfa-api-v2.service \
    akamai-mfa-mcp-v2.service
do
    systemctl is-active --quiet "$unit" || fail "inactive_$unit"
done

/opt/akamai-mfa/bin/wait-postgres-v2-ready.sh
/opt/akamai-mfa/bin/wait-api-v2-ready.sh
/opt/akamai-mfa/bin/wait-mcp-v2-ready.sh

podman exec akamai-mfa-api-v2 \
    sh -lc 'test "${EXECUTION_BACKEND:-}" = simulation' \
    || fail api_execution_backend_not_simulation

podman exec akamai-mfa-mcp-v2 \
    sh -lc 'test "${MCP_DESTRUCTIVE_EXECUTION_MODE:-}" = disabled' \
    || fail mcp_destructive_mode_not_disabled

echo "SAFE_STATE=PASS"
echo "SMOKE=PASS"
