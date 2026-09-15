# CHANGESET-08 — Akamai MFA Device DELETE Tenant Validation

Target: `akamai-mfa-api 0.8.0-v2-dev`

## Purpose

Introduce the frozen normal Akamai MFA reset primitive: remove exactly one
backend-bound eligible device, never the whole Akamai MFA account.

## Real primitive

```text
DELETE /amfa/v1/devices/{deviceId}?contractId=...
```

Expected tenant response: HTTP 204.

The device ID is selected and stored only by the API backend. It never appears in
the public API, MCP arguments, model context or operator response.

## Backend

Default remains:

```text
EXECUTION_BACKEND=disabled
```

Controlled validation:

```text
EXECUTION_BACKEND=akamai_mfa_validation
```

This backend supports only `AKAMAI_MFA_DEVICE_RESET`.

EAA operations are rejected before execution claim, so their confirmation is not
consumed.

## Safety / transport policy

There is no destructive retry.

- HTTP 204 -> expected transport outcome, then mandatory post-check
- timeout / unknown / HTTP 5xx -> ambiguous, inspect state
- HTTP 404 after successful preflight -> ambiguous, inspect state
- unexpected successful 2xx -> ambiguous, inspect state
- other 4xx -> conclusive failure

## Mandatory post-check

Success requires all of the following:

1. exact target device is absent;
2. Akamai MFA account is still present;
3. every non-target factor from the prepare baseline is preserved;
4. every protected factor is preserved.

The internal factor baseline is stored only inside the operation's internal
destructive state. Public `prepared_snapshot` stays sanitized.

Outcomes:

- target absent + account present + all non-target/protected preserved -> SUCCEEDED
- ambiguous DELETE + target remains -> REQUIRES_RECONFIRMATION
- expected 204 + target remains -> FAILED
- account disappeared -> FAILED
- any protected/non-target factor disappeared -> FAILED
- post-check unavailable -> VERIFYING

`PROVISIONED` is allowed but is not itself the success criterion.

## Still absent

- automatic child retry creation
- MCP v2 integration
- production enablement
- final resolution of EAA OTP post-check gap
