# CHANGESET-02B — Probe safe-ref hotfix

Target: `akamai-mfa-mcp 0.5.0-v2-dev`

## Root cause

The CS02A probe invoked `prepare_eaa_otp_reset` with:

```text
usr_probe_safe
```

The MCP's frozen safe-ref validator requires:

```text
usr_[A-Za-z0-9_-]{20,125}
```

so the tool raised `ValueError` before the interaction-attestation code could
run.

## Fix

The probe now uses the syntactically valid, fictitious value:

```text
usr_00000000000000000000
```

This does not identify a tenant user and is never sent to the API because the
CS02 prepare tool remains a local fail-closed stub.

A regression test imports the same `normalize_user_ref` validator and verifies
the probe constant before packaging.

## Unchanged

- MCP server behavior
- tool schemas
- request-header attestation implementation
- stateless HTTP transport
- API read-only calls
- destructive enablement (still disabled)
- no prepare/confirm/execute/retry API calls
