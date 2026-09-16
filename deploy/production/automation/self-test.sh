#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROD_DIR=$(CDPATH= cd -- "$BASE_DIR/.." && pwd)

fail() {
    echo "AUTOMATION_SELF_TEST=FAIL reason=$1" >&2
    exit 1
}

for f in \
    common.sh \
    host-preflight.sh \
    pull-images.sh \
    render-env.sh \
    provision-secrets.sh \
    bootstrap-db.sh \
    rollback.sh \
    deploy-production.sh \
    self-test.sh
do
    sh -n "$BASE_DIR/$f" || fail "shell_syntax_$f"
done
echo "SHELL_SYNTAX=PASS"

# Load immutable identity constants only; common.sh has no side effects.
. "$BASE_DIR/common.sh"

grep -Fx "Image=$API_REF" "$PROD_DIR/quadlets/akamai-mfa-api-v2.container" >/dev/null \
    || fail api_quadlet_ref_mismatch
grep -Fx "Image=$MCP_REF" "$PROD_DIR/quadlets/akamai-mfa-mcp-v2.container" >/dev/null \
    || fail mcp_quadlet_ref_mismatch
grep -Fx "Image=$PG_REF" "$PROD_DIR/quadlets/akamai-mfa-postgres-v2.container" >/dev/null \
    || fail postgres_quadlet_ref_mismatch
echo "IMMUTABLE_REFS=PASS"

grep -Fx 'Description=Akamai MFA MCP v2 candidate' \
    "$PROD_DIR/quadlets/akamai-mfa-mcp-v2.container" >/dev/null \
    || fail mcp_canonical_description_mismatch

grep -Fx 'EXECUTION_BACKEND=simulation' "$PROD_DIR/env/api-v2.env.example" >/dev/null \
    || fail api_safe_state_missing
grep -Fx 'MCP_DESTRUCTIVE_EXECUTION_MODE=disabled' "$PROD_DIR/env/mcp-v2.env.example" >/dev/null \
    || fail mcp_safe_state_missing
echo "SAFE_STATE_TEMPLATES=PASS"

# Deployment-specific non-secret values must remain placeholders in examples.
for key in AKAMAI_CONNECT_TIMEOUT AKAMAI_READ_TIMEOUT LOG_LEVEL SIMULATION_PRIMITIVE_OUTCOME SIMULATION_POSTCHECK_OUTCOME; do
    grep -Fx "$key=CHANGE_ME" "$PROD_DIR/env/api-v2.env.example" >/dev/null \
        || fail "api_example_not_sanitized_$key"
done
for key in MFA_API_URL MFA_API_TIMEOUT MCP_HOST MCP_PORT MCP_LOG_LEVEL MCP_TRUSTED_INGRESS_MODE MCP_TRUSTED_CONTEXT_MODE; do
    grep -Fx "$key=CHANGE_ME" "$PROD_DIR/env/mcp-v2.env.example" >/dev/null \
        || fail "mcp_example_not_sanitized_$key"
done
echo "SANITIZED_EXAMPLES=PASS"

# The automation config must not accept secret material.
if grep -Eq '^[A-Z0-9_]*(PASSWORD|TOKEN|SECRET|DATABASE_URL)=' "$BASE_DIR/production.conf.example"; then
    fail secret_key_present_in_production_conf_example
fi
echo "NON_SECRET_CONFIG=PASS"

echo "AUTOMATION_SELF_TEST=PASS"
