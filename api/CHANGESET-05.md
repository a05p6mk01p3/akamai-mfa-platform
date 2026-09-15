# CHANGESET-05 — Confirm-only Operations

Target: `akamai-mfa-api 0.8.0-v2-dev`

## Adds

- `POST /v2/operations/{operation_id}/confirm`
- confirmation requires:
  - matching `X-MFA-Actor`
  - matching `X-MFA-Session`
  - `X-MFA-Interaction`
  - interaction distinct from the prepare interaction
  - operation state `PREPARED`
  - unexpired operation TTL
- `PREPARED -> CONFIRMED`
- `CONFIRMATION_ACCEPTED` event in the same transaction
- expired PREPARED operations become `EXPIRED` transactionally on confirm attempt
- replay confirmation is rejected
- precise safe error codes for context, expiry, interaction reuse, and state conflict

## Still absent

- public `/execute` endpoint
- upstream EAA OTP reset primitive
- upstream Akamai MFA device DELETE primitive
- post-check execution
- ambiguity recovery/retry child operations
- MCP v2 changes

`destructive_operations_enabled` remains `false`.

## Confirmation boundary

The API accepts an adapter/runtime-attested interaction reference through
`X-MFA-Interaction`. It must differ from the interaction stored at prepare time.

There is no `confirmed=true` body parameter.

The future MCP adapter is responsible for calling this endpoint only after a later
human interaction. The model does not choose or receive the interaction reference.

## Replay

After one successful confirmation:

`PREPARED -> CONFIRMED`

a second confirmation request cannot confirm the same operation again.

The confirmation is not yet consumed for destructive execution in this change-set,
because no public execute endpoint exists.
