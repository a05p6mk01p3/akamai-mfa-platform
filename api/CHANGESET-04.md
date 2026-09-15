# CHANGESET-04 — Prepare-only Operations

Target: `akamai-mfa-api 0.8.0-v2-dev`

## Adds

- `POST /v2/eaa-native-mfa/otp-reset/prepare`
- `POST /v2/akamai-mfa/device-reset/prepare`
- `GET /v2/operations/{operation_id}`
- prepare-only `OperationManager`
- mandatory internal `X-MFA-Interaction` on prepare
- EAA identity revalidation before operation creation
- Akamai factor rediscovery/classification before operation creation
- multiple eligible authenticators require explicit `device_ref`
- selected `device_ref` is re-resolved and revalidated against current state
- exactly one internal destructive target is bound in PostgreSQL
- public prepare responses contain no internal destructive IDs

## Still absent

- `POST /v2/operations/{operation_id}/confirm`
- `POST /v2/operations/{operation_id}/execute`
- EAA OTP mutation primitive
- Akamai MFA device DELETE primitive
- post-check execution
- ambiguous-result execution handling
- MCP v2 changes

`destructive_operations_enabled` remains `false`.

## Interaction semantics

`X-MFA-Interaction` is adapter/runtime context used to record the interaction in
which prepare occurred. It is not human confirmation.

Later confirmation must use a distinct interaction reference and remains
unexposed in this change-set.

## Akamai prepare behavior

- zero eligible factors -> no operation
- `already_awaiting_enrollment` -> no operation
- one eligible factor -> API may bind it without device_ref
- multiple eligible factors -> `device_selection_required`
- provided device_ref -> resolve + re-fetch + reclassify + bind exactly one current eligible factor
- stale/noneligible device_ref -> fail closed, no operation
