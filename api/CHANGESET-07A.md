# CHANGESET-07A — Truthful Execution Metadata Hotfix

Target: `akamai-mfa-api 0.8.0-v2-dev`

This hotfix corrects a development-contract bug found during the first real EAA
tenant-validation execution.

## Bug

CS07 inherited this CS06 response field:

```json
"simulation": true
```

as a Pydantic `Literal[true]`.

Therefore a real `EXECUTION_BACKEND=eaa_validation` operation incorrectly
reported itself as simulation even though the EAA OTP reset POST was real.

## Fix

- `simulation` is now a boolean.
- It is derived from the configured execution backend:
  - `simulation` backend -> `true`
  - `eaa_validation` backend -> `false`
- Verification observations preserve the safe primitive metadata, including:
  - primitive disposition
  - safe primitive code
  - upstream status when available
  - whether external mutation was performed/ambiguous
- No internal IDs are added to public responses.

## EAA post-check status

The first real tenant validation showed:

- reset POST accepted upstream;
- EAA user remained exact/resolvable;
- `login_mfa` remained true;
- `otp_reset_available` remained true;
- no usable Admin Event Report match was found.

Therefore the EAA operation must remain `VERIFYING`. No success criterion is
introduced by this hotfix.

## Safety

Do not re-execute the already-consumed operation and do not repeat a reset merely
to test this metadata correction.
