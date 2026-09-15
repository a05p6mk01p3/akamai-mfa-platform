# Change-set 01 — read-only foundation

## Goal

Create the v2 domain/client foundation without making any upstream mutation possible.

## Important design choices

1. `AkamaiEaaClient` is split into `EaaClient` and `AkamaiMfaClient`.
2. `deviceCount` is no longer used as reset authority.
3. Akamai MFA account lookup requests actual observed devices with `includeDevices=true`.
4. Device classification is a pure deny-by-default policy.
5. No method in the new clients issues POST/DELETE destructive calls.
6. Public `/v2/...` routes are deliberately deferred until safe-reference/context persistence is implemented; returning contract-incomplete IDs would be worse than exposing no route.
7. PostgreSQL (ADR-007) will be introduced before operation lifecycle endpoints.

## Next validation

Use sanitized/tenant responses to confirm the exact upstream device payload fields (`deviceType`, `createdBy`, `externalTag`, `deviceId`, platform field) and adjust parsing contract tests if the tenant differs.
