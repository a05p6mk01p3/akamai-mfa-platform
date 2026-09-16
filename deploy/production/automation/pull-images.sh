#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RESULT_LABEL=PULL_IMAGES
. "$BASE_DIR/common.sh"

MODE=pull
AUTHFILE=''

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check-only) MODE=check ;;
        --authfile)
            shift
            [ "$#" -gt 0 ] || fail missing_authfile_argument
            AUTHFILE=$1
            ;;
        -h|--help)
            echo "usage: $0 [--check-only] [--authfile FILE]"
            exit 0
            ;;
        *) fail "unknown_argument_$1" ;;
    esac
    shift
done

require_root
require_cmd podman
if [ -n "$AUTHFILE" ]; then
    require_protected_file "$AUTHFILE"
fi

inspect_identity() {
    ref=$1
    expected_id=$2
    label=$3

    id=$(podman image inspect "$ref" --format '{{.Id}}' 2>/dev/null || true)
    digest=$(podman image inspect "$ref" --format '{{.Digest}}' 2>/dev/null || true)
    [ -n "$id" ] || return 1
    [ "$id" = "$expected_id" ] || fail "${label}_image_id_mismatch"
    case "$ref" in
        *@sha256:*) expected_digest=sha256:${ref##*@sha256:} ;;
        *) fail "${label}_reference_not_digest_pinned" ;;
    esac
    [ "$digest" = "$expected_digest" ] || fail "${label}_digest_mismatch"
    echo "${label}_IMAGE_IDENTITY=PASS"
    return 0
}

inspect_digest_only() {
    ref=$1
    label=$2
    digest=$(podman image inspect "$ref" --format '{{.Digest}}' 2>/dev/null || true)
    [ -n "$digest" ] || return 1
    case "$ref" in
        *@sha256:*) expected_digest=sha256:${ref##*@sha256:} ;;
        *) fail "${label}_reference_not_digest_pinned" ;;
    esac
    [ "$digest" = "$expected_digest" ] || fail "${label}_digest_mismatch"
    echo "${label}_IMAGE_IDENTITY=PASS"
    return 0
}

if [ "$MODE" = check ]; then
    if inspect_identity "$API_REF" "$API_ID" API; then :; else echo "API_IMAGE_LOCAL=ABSENT"; fi
    if inspect_identity "$MCP_REF" "$MCP_ID" MCP; then :; else echo "MCP_IMAGE_LOCAL=ABSENT"; fi
    if inspect_digest_only "$PG_REF" POSTGRES; then :; else echo "POSTGRES_IMAGE_LOCAL=ABSENT"; fi
    echo "PULL_IMAGES=CHECK_PASS"
    exit 0
fi

pull_ref() {
    ref=$1
    if [ -n "$AUTHFILE" ]; then
        podman pull --authfile "$AUTHFILE" "$ref" >/dev/null
    else
        podman pull "$ref" >/dev/null
    fi
}

pull_ref "$API_REF"
pull_ref "$MCP_REF"
pull_ref "$PG_REF"

inspect_identity "$API_REF" "$API_ID" API || fail api_image_missing_after_pull
inspect_identity "$MCP_REF" "$MCP_ID" MCP || fail mcp_image_missing_after_pull
inspect_digest_only "$PG_REF" POSTGRES || fail postgres_image_missing_after_pull

echo "PULL_IMAGES=PASS"
