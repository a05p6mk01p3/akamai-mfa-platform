# CHANGESET-12 — Unified destructive execution backend

## Problem

`EXECUTION_BACKEND` was carrying two independent responsibilities: choosing simulation versus real execution, and selecting one destructive domain (`eaa_validation` or `akamai_mfa_validation`). This made the operator-facing state ambiguous: destructive mode could report enabled while the requested domain still failed with `execution_backend_disabled`.

## Decision

The operator-facing API execution modes are now:

- `disabled` — fail closed; execution framework unavailable.
- `simulation` — full state-machine validation with no upstream mutation.
- `live` — destructive framework enabled for both supported domains.

Domain separation is preserved below the operational gate. The persisted `operation_type` dispatches to exactly one domain-local adapter:

- `EAA_NATIVE_MFA_OTP_RESET` -> EAA tenant-validation adapter.
- `AKAMAI_MFA_DEVICE_RESET` -> Akamai MFA tenant-validation adapter.

The MCP master gate remains `MCP_DESTRUCTIVE_EXECUTION_MODE=disabled|enabled`.

## Safety invariants

- No generic cross-domain destructive primitive is introduced.
- An EAA operation can never fall through to the Akamai MFA adapter, and vice versa.
- Unknown operation types fail closed before mutation.
- Backend-owned destructive targets, later-human confirmation, no blind retry, and domain-local post-check behavior are unchanged.
- Legacy API values `eaa_validation` and `akamai_mfa_validation` are rejected by configuration rather than silently mapped.

## Compatibility / rollout

The frozen `v2.0.0` tag is not modified. This change requires a new API image/release line. Deploy the new image first with `EXECUTION_BACKEND=simulation`; only use `live` inside an explicitly controlled destructive window. Rollback to the frozen image requires returning `EXECUTION_BACKEND` to `simulation` first because the old image does not understand `live`.

## Tests

CS12 adds tests for:

- single destructive `live` mode;
- rejection of legacy per-domain execution modes;
- EAA operation dispatch only to EAA;
- Akamai MFA operation dispatch only to Akamai MFA;
- malformed cross-domain target shape failing without cross-dispatch;
- unknown operation type failing closed.
