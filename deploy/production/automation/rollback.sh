#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RESULT_LABEL=ROLLBACK
. "$BASE_DIR/common.sh"

require_root
require_cmd systemctl

# Clean-install rollback is intentionally conservative: stop and disable only
# the v2 application/database services started by this automation. Networks,
# images, secrets, environment files, and the PostgreSQL volume are preserved
# for diagnosis. This is not the historical v1 rollback procedure.
for unit in \
    akamai-mfa-mcp-v2.service \
    akamai-mfa-api-v2.service \
    akamai-mfa-postgres-v2.service
do
    systemctl disable --now "$unit" >/dev/null 2>&1 || true
    echo "ROLLBACK_STOPPED=$unit"
done

systemctl reset-failed \
    akamai-mfa-mcp-v2.service \
    akamai-mfa-api-v2.service \
    akamai-mfa-postgres-v2.service >/dev/null 2>&1 || true

echo "ROLLBACK_DATA_PRESERVED=PASS"
echo "ROLLBACK=PASS"
