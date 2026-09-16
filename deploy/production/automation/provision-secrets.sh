#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RESULT_LABEL=PROVISION_SECRETS
. "$BASE_DIR/common.sh"

MODE=''
SECRETS_DIR=/run/akamai-mfa-secrets
REUSE_EXISTING=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check-only) MODE=check ;;
        --apply) MODE=apply ;;
        --secrets-dir)
            shift
            [ "$#" -gt 0 ] || fail missing_secrets_dir_argument
            SECRETS_DIR=$1
            ;;
        --reuse-existing) REUSE_EXISTING=1 ;;
        -h|--help)
            echo "usage: $0 (--check-only|--apply) [--secrets-dir DIR] [--reuse-existing]"
            exit 0
            ;;
        *) fail "unknown_argument_$1" ;;
    esac
    shift
done

[ -n "$MODE" ] || fail mode_required
require_root
require_cmd podman
require_cmd stat

SECRETS='akamai-mfa-pg-v2-password akamai-mfa-api-v2-client-token akamai-mfa-api-v2-client-secret akamai-mfa-api-v2-access-token akamai-mfa-api-v2-database-url akamai-mfa-mcp-ingress-token'

# Phase 1 is intentionally non-mutating. Validate the complete secret set before
# creating any Podman secret so a later conflict cannot leave a partial install.
for name in $SECRETS; do
    if podman secret inspect "$name" >/dev/null 2>&1; then
        if [ "$MODE" = check ]; then
            echo "SECRET_READY=$name source=podman"
            continue
        fi
        [ "$REUSE_EXISTING" -eq 1 ] || fail "existing_secret_requires_reuse_flag_$name"
        continue
    fi

    src="$SECRETS_DIR/$name"
    require_protected_file "$src"
    if [ "$MODE" = check ]; then
        echo "SECRET_READY=$name source=file"
    fi
done

if [ "$MODE" = check ]; then
    echo "PROVISION_SECRETS=CHECK_PASS"
    exit 0
fi

# Phase 2 mutates only after every secret has passed phase 1.
for name in $SECRETS; do
    if podman secret inspect "$name" >/dev/null 2>&1; then
        echo "SECRET_REUSED=$name"
        continue
    fi

    src="$SECRETS_DIR/$name"
    podman secret create "$name" "$src" >/dev/null
    podman secret inspect "$name" >/dev/null 2>&1 || fail "secret_create_verification_failed_$name"
    echo "SECRET_CREATED=$name"
done

echo "PROVISION_SECRETS=PASS"
