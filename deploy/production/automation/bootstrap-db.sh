#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RESULT_LABEL=DB_BOOTSTRAP
. "$BASE_DIR/common.sh"

MODE=apply
while [ "$#" -gt 0 ]; do
    case "$1" in
        --check-only) MODE=check ;;
        -h|--help)
            echo "usage: $0 [--check-only]"
            exit 0
            ;;
        *) fail "unknown_argument_$1" ;;
    esac
    shift
done

require_root
require_cmd podman
require_cmd systemctl

if ! systemctl is-active --quiet akamai-mfa-postgres-v2.service; then
    if [ "$MODE" = check ]; then
        echo "DB_SCHEMA_CHECK=SKIPPED reason=postgres_inactive"
        echo "DB_BOOTSTRAP=CHECK_PASS"
        exit 0
    fi
    fail postgres_service_inactive
fi

/opt/akamai-mfa/bin/wait-postgres-v2-ready.sh

REPO_ROOT=$(CDPATH= cd -- "$BASE_DIR/../../.." && pwd)
MIGRATION="$REPO_ROOT/api/migrations/001_v2_repository.sql"
[ -f "$MIGRATION" ] || fail missing_migration_001_v2_repository_sql

exists_table() {
    table=$1
    printf "SELECT CASE WHEN to_regclass('public.%s') IS NULL THEN 0 ELSE 1 END;\n" "$table" |
        podman exec -i akamai-mfa-postgres-v2 \
            sh -lc 'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"' |
        tr -d '[:space:]'
}

ops=$(exists_table operations)
events=$(exists_table operation_events)
refs=$(exists_table safe_references)
state="${ops}${events}${refs}"

case "$state" in
    111)
        echo "DB_SCHEMA=READY"
        echo "DB_BOOTSTRAP=PASS"
        exit 0
        ;;
    000)
        if [ "$MODE" = check ]; then
            echo "DB_SCHEMA=EMPTY"
            echo "DB_BOOTSTRAP=CHECK_PASS"
            exit 0
        fi
        ;;
    *) fail "partial_schema_detected_$state" ;;
esac

cat "$MIGRATION" |
    podman exec -i akamai-mfa-postgres-v2 \
        sh -lc 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null

ops=$(exists_table operations)
events=$(exists_table operation_events)
refs=$(exists_table safe_references)
[ "${ops}${events}${refs}" = 111 ] || fail schema_verification_failed

echo "DB_SCHEMA=READY"
echo "DB_BOOTSTRAP=PASS"
