#!/bin/sh
set -eu

fail() {
    echo "PREFLIGHT=FAIL reason=$1" >&2
    exit 1
}

[ "$(id -u)" -eq 0 ] || fail root_required

for cmd in podman systemctl grep stat; do
    command -v "$cmd" >/dev/null 2>&1 || fail "missing_command_$cmd"
done

for f in \
    /opt/akamai-mfa/config/postgres-v2/postgres-v2.env \
    /opt/akamai-mfa/config/api-v2/api-v2.env \
    /opt/akamai-mfa/config/mcp-v2/mcp-v2.env
do
    [ -f "$f" ] || fail "missing_env_file_$f"
    [ "$(stat -c '%U' "$f")" = root ] || fail "env_not_root_owned_$f"
    [ "$(stat -c '%G' "$f")" = root ] || fail "env_not_root_group_$f"
    mode=$(stat -c '%a' "$f")
    case "$mode" in
        400|600|640) ;;
        *) fail "env_permissions_$f=$mode" ;;
    esac
    if grep -q 'CHANGE_ME' "$f"; then
        fail "placeholder_present_$f"
    fi
done

grep -qx 'EXECUTION_BACKEND=simulation' \
    /opt/akamai-mfa/config/api-v2/api-v2.env \
    || fail api_execution_backend_not_simulation

grep -qx 'MCP_DESTRUCTIVE_EXECUTION_MODE=disabled' \
    /opt/akamai-mfa/config/mcp-v2/mcp-v2.env \
    || fail mcp_destructive_mode_not_disabled

for secret in \
    akamai-mfa-pg-v2-password \
    akamai-mfa-api-v2-client-token \
    akamai-mfa-api-v2-client-secret \
    akamai-mfa-api-v2-access-token \
    akamai-mfa-api-v2-database-url \
    akamai-mfa-mcp-ingress-token
do
    podman secret inspect "$secret" >/dev/null 2>&1 \
        || fail "missing_podman_secret_$secret"
done

API_REF='ghcr.io/a05p6mk01p3/akamai-mfa-api@sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af'
MCP_REF='ghcr.io/a05p6mk01p3/akamai-mfa-mcp@sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d'
PG_REF='docker.io/library/postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'

for ref in "$API_REF" "$MCP_REF" "$PG_REF"; do
    podman image inspect "$ref" >/dev/null 2>&1 \
        || fail "missing_image_$ref"
done

for f in \
    /etc/containers/systemd/akamai-mfa.network \
    /etc/containers/systemd/librechat.network \
    /etc/containers/systemd/akamai-mfa-postgres-v2.container \
    /etc/containers/systemd/akamai-mfa-api-v2.container \
    /etc/containers/systemd/akamai-mfa-mcp-v2.container \
    /opt/akamai-mfa/bin/akamai-mfa-api-v2-entrypoint.sh \
    /opt/akamai-mfa/bin/wait-postgres-v2-ready.sh \
    /opt/akamai-mfa/bin/wait-api-v2-ready.sh \
    /opt/akamai-mfa/bin/wait-mcp-v2-ready.sh
do
    [ -f "$f" ] || fail "missing_installed_file_$f"
done

systemctl daemon-reload

for unit in \
    akamai-mfa-network.service \
    librechat-network.service \
    akamai-mfa-postgres-v2.service \
    akamai-mfa-api-v2.service \
    akamai-mfa-mcp-v2.service
do
    systemctl cat "$unit" >/dev/null 2>&1 || fail "unit_not_generated_$unit"
done

echo "PREFLIGHT=PASS"
