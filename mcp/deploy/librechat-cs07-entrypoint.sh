#!/bin/sh
set -eu

SECRET_FILE=/run/secrets/akamai-mfa-mcp-ingress-token

if [ ! -r "$SECRET_FILE" ] || [ ! -s "$SECRET_FILE" ]; then
    echo "fatal: trusted ingress secret is unavailable" >&2
    exit 78
fi

AKAMAI_MFA_MCP_INGRESS_TOKEN="$(cat "$SECRET_FILE")"
if [ -z "$AKAMAI_MFA_MCP_INGRESS_TOKEN" ]; then
    echo "fatal: trusted ingress secret is empty" >&2
    exit 78
fi
export AKAMAI_MFA_MCP_INGRESS_TOKEN

exec npm run backend
