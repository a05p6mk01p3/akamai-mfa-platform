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
require_cmd tr

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

psql_scalar() {
    sql=$1
    printf '%s\n' "$sql" |
        podman exec -i akamai-mfa-postgres-v2 \
            sh -lc 'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"' |
        tr -d '[:space:]'
}

exists_relation() {
    psql_scalar "SELECT CASE WHEN to_regclass('public.$1') IS NULL THEN 0 ELSE 1 END;"
}

exists_constraint() {
    psql_scalar "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '$1') THEN 1 ELSE 0 END;"
}

schema_state() {
    printf '%s%s%s%s%s%s%s%s%s%s' \
        "$(exists_relation operations)" \
        "$(exists_relation operation_events)" \
        "$(exists_relation safe_references)" \
        "$(exists_relation idx_operations_status_expires)" \
        "$(exists_relation idx_operations_parent)" \
        "$(exists_relation idx_operation_events_operation_time)" \
        "$(exists_relation idx_safe_references_expiry)" \
        "$(exists_constraint ck_operations_status)" \
        "$(exists_constraint ck_operations_parent_not_self)" \
        "$(exists_constraint ck_safe_reference_type)"
}

state=$(schema_state)
case "$state" in
    1111111111)
        echo "DB_SCHEMA=READY"
        echo "DB_BOOTSTRAP=PASS"
        exit 0
        ;;
    0000000000)
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

state=$(schema_state)
[ "$state" = 1111111111 ] || fail "schema_verification_failed_$state"

echo "DB_SCHEMA=READY"
echo "DB_BOOTSTRAP=PASS"
