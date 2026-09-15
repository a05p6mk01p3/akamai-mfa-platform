# CHANGESET-03 — Read-only API v2 + Safe References

Target: `akamai-mfa-api 0.8.0-v2-dev`

## Adds

- `GET /v2/eaa/users/search?q=...`
- opaque `user_ref` issuance persisted in PostgreSQL;
- `GET /v2/akamai-mfa/users/{user_ref}/status`;
- `device_ref` only for eligible `USER + AKAMAI_AUTHENTICATOR` factors;
- `selection_required=true` when more than one eligible authenticator is observed;
- mandatory contextual binding through internal headers:
  - `X-MFA-Actor`
  - `X-MFA-Session`
- safe error mapping for expired/missing/wrong-context references;
- direct-execution fix for `scripts/db_migrate.py` and `scripts/db_check.py`.

## Still absent

- EAA OTP mutation;
- Akamai MFA DELETE;
- prepare endpoints;
- confirmation endpoints;
- execution endpoints;
- OperationManager destructive orchestration;
- MCP v2 changes.

`destructive_operations_enabled` remains `false`.

## Context headers

The two headers are an internal correlation interface for this implementation phase.
They are not a claim that caller authentication/authorization is complete.

The future MCP adapter will provide contextual values; the model/operator will not
receive or choose internal IDs.

## Safe-reference domains

`user_ref`:
- reference type: `USER`
- domain: `identity`
- may be consumed by domain-specific read-only services

`device_ref`:
- reference type: `DEVICE`
- domain: `akamai_mfa`
- emitted only for reset-eligible authenticators

Protected/unknown factors never receive `device_ref`.
