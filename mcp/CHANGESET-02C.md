# CHANGESET-02C — Safe interaction fingerprint observability

Target: `akamai-mfa-mcp 0.5.0-v2-dev`

## Purpose

Prove that successive human interactions arriving through LibreChat produce
different runtime interaction references, without logging the raw reference.

## Behavior

When `MCP_LOG_ATTESTATION_PROBE=true`, successful request-header attestation
logs a 12-character fingerprint together with source and stateless-session
presence.

The fingerprint is HMAC-SHA256 truncated to 12 hexadecimal characters with a
random process-local key.

Properties:

- raw interaction reference is never logged;
- fingerprint is deterministic only within one MCP process lifetime;
- restart changes the process-local key;
- no fingerprint is persisted;
- this is development observability, not identity/authentication.

## Expected validation

Two separate human messages in one running MCP process should produce distinct
fingerprints. A repeated tool call inside the same human interaction may
legitimately keep the same fingerprint.

## Unchanged

- six public tool schemas;
- `stateless_http=True`;
- request-header attestation semantics;
- read-only API tools;
- four non-read-only tools remain fail-closed;
- zero API prepare/confirm/execute/retry calls.
