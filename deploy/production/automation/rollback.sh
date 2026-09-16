#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RESULT_LABEL=ROLLBACK
. "$BASE_DIR/common.sh"

require_root
for cmd in systemctl ln; do require_cmd "$cmd"; done

APP_UNITS='akamai-mfa-mcp-v2.service akamai-mfa-api-v2.service akamai-mfa-postgres-v2.service'

# Clean-install rollback is intentionally conservative: stop and persistently
# mask only the v2 application/database services started by this automation.
# Quadlet-generated services cannot be disabled with `systemctl disable`; their
# [Install] wiring is regenerated at boot, so masking is the fail-closed way to
# keep them stopped across reboot. Networks, images, secrets, environment files,
# installed Quadlets, and the PostgreSQL volume are preserved for diagnosis.
# This is not the historical v1 rollback procedure.
for unit in $APP_UNITS; do
    systemctl stop "$unit" >/dev/null 2>&1 || true
    if ! systemctl mask "$unit" >/dev/null 2>&1; then
        ln -sfn /dev/null "/etc/systemd/system/$unit"
    fi
    echo "ROLLBACK_STOPPED=$unit"
done

systemctl daemon-reload

for unit in $APP_UNITS; do
    state=$(systemctl is-enabled "$unit" 2>/dev/null || true)
    [ "$state" = masked ] || fail "unit_not_masked_$unit"
    echo "ROLLBACK_MASKED=$unit"
done

systemctl reset-failed $APP_UNITS >/dev/null 2>&1 || true

echo "ROLLBACK_DATA_PRESERVED=PASS"
echo "ROLLBACK=PASS"
