#!/bin/sh

API_REF='ghcr.io/a05p6mk01p3/akamai-mfa-api@sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af'
API_ID='650a0e1b1dedb1f696cc34feac334c5fb9da59a2d8fcabf3a348f50e19814512'
MCP_REF='ghcr.io/a05p6mk01p3/akamai-mfa-mcp@sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d'
MCP_ID='d865a90ea546edcf7df039b2007e1f31528acc174d98fec513d957e15264d213'
PG_REF='docker.io/library/postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'

fail() {
    label=${RESULT_LABEL:-AUTOMATION}
    echo "${label}=FAIL reason=$1" >&2
    exit 1
}

require_root() {
    [ "$(id -u)" -eq 0 ] || fail root_required
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "missing_command_$1"
}

require_protected_file() {
    f=$1
    [ -f "$f" ] || fail "missing_file_$f"
    [ ! -L "$f" ] || fail "symlink_not_allowed_$f"
    [ "$(stat -c '%U' "$f")" = root ] || fail "file_not_root_owned_$f"
    [ "$(stat -c '%G' "$f")" = root ] || fail "file_not_root_group_$f"
    mode=$(stat -c '%a' "$f")
    case "$mode" in
        400|600|640) ;;
        *) fail "unsafe_file_permissions_${f}=$mode" ;;
    esac
}

get_config_value() {
    cfg=$1
    key=$2
    count=$(grep -c "^${key}=" "$cfg" 2>/dev/null || true)
    [ "$count" -eq 1 ] || fail "config_key_count_${key}=$count"
    value=$(grep "^${key}=" "$cfg" | cut -d= -f2-)
    [ -n "$value" ] || fail "config_value_empty_$key"
    [ "$value" != CHANGE_ME ] || fail "config_placeholder_$key"
    printf '%s' "$value"
}

script_dir() {
    CDPATH= cd -- "$(dirname -- "$1")" && pwd
}
