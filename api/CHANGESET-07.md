# CHANGESET-07 — EAA OTP Tenant-Validation Backend

Target: `akamai-mfa-api 0.8.0-v2-dev`

## Purpose

Introduce the already tenant-validated EAA OTP reset upstream contract while
**not guessing the tenant's exact post-reset success criterion**.

This is a controlled validation change-set, not a production-ready EAA live
backend.

## Real primitive introduced

EAA only:

```text
POST /crux/v1/mgmt-pop/tenant/mfa/reset?contractId=...
{
  "otp_type": "login_mfa",
  "user_id": <backend-bound internal reset id>
}
```

The internal reset id and contract id never enter the public API or MCP/model
surface.

There is no automatic retry.

## Execution backend

Default remains fail-closed:

```text
EXECUTION_BACKEND=disabled
```

Simulation remains available:

```text
EXECUTION_BACKEND=simulation
```

Controlled tenant validation:

```text
EXECUTION_BACKEND=eaa_validation
```

`eaa_validation` can perform a real EAA OTP reset and supports only
`EAA_NATIVE_MFA_OTP_RESET`.

An Akamai MFA device-reset operation is rejected before the atomic execution
claim; its confirmation is not consumed.

## Transport result policy

- accepted upstream response -> primitive `EXPECTED`, then mandatory observation
- timeout / connection ambiguity / HTTP 5xx -> primitive `AMBIGUOUS`, then observation
- conclusive HTTP 4xx -> `FAILED`
- no blind retry in any branch

## Post-check policy in CS07

The G2 freeze requires the exact EAA post-reset state to be tenant-validated.

Therefore CS07 deliberately does not interpret `login_mfa` or
`otp_reset_available` as success.

The EAA-only post-check records safe observations:

- exact identity resolved
- account/user status
- `login_mfa`
- `otp_reset_available`

and always remains `VERIFYING` with:

```text
EAA_POSTCHECK_TENANT_VALIDATION_REQUIRED
```

until the post-reset criterion is explicitly validated and frozen.

Akamai MFA is neither read nor modified by the EAA post-check.

## Safety

Do not enable `eaa_validation` against a normal user merely to smoke-test the
container. It is destructive: it can reset the selected user's EAA Native MFA OTP.

Use a disposable/approved validation identity only.

## Still absent

- final EAA post-reset success criterion
- production EAA live backend
- Akamai MFA device DELETE
- child retry operation creation
- MCP v2 integration
