# Akamai MFA Platform v2 — G5 Release Checklist

**Status:** COMPLETE — G5 PASS  
**Release basis:** post-CS11 canonical state  
**Release date:** 2026-09-15

## Artifact freeze

- [x] Clean API source bundle; no `__pycache__` / `.pyc`.
- [x] Clean MCP source bundle; no `__pycache__` / `.pyc`.
- [x] Source bundles extracted and matched approved source trees.
- [x] Source bundle SHA-256 checksums recorded and verified.
- [x] API final tag `0.8.0` minted from approved canonical image ID without rebuild.
- [x] MCP final tag `0.5.0` minted from approved canonical image ID without rebuild.
- [x] Final image IDs and digests recorded.
- [x] API final image proven to contain CS10 search-refinement code.
- [x] MCP final image/source hashes and CS11-FIX canonical gate verified.

## Documentation freeze

- [x] Functional specification frozen for final release.
- [x] Architecture updated for final image identities, post-CS11 snapshot and expiry correlation behavior.
- [x] API contract frozen.
- [x] MCP contract updated for `prepared_operation_expired`.
- [x] Test/security matrix updated through CS11-FIX/G5.
- [x] Release plan closed.
- [x] CS10 historical evidence preserved.
- [x] CS11/CS11-FIX evidence created.
- [x] Final release notes created.
- [x] Final operator/rollback notes created and aligned to frozen v1.
- [x] Agent/project instructions reviewed for `q`, >5 refinement, later confirmation and domain separation.

## Controlled destructive validation

- [x] Dedicated test account read-only preflight passed.
- [x] Real Akamai MFA prepare=1.
- [x] Later explicit human confirmation passed.
- [x] API confirm=1.
- [x] API execute=1.
- [x] Automatic destructive retry=0.
- [x] Target-absent post-check passed.
- [x] Independent tenant post-check passed; account preserved and eligible factor count after reset=0.
- [x] Canonical MCP restored to destructive `disabled`.
- [x] Canonical API restored to execution backend `simulation`.
- [x] Expired-operation diagnostic fixed and regression-tested (`109/109`).

## Final non-destructive smoke

- [x] PostgreSQL/API/MCP/LibreChat active.
- [x] API `/ready` HTTP 200.
- [x] MCP points to canonical API.
- [x] `MCP_DESTRUCTIVE_EXECUTION_MODE=disabled`.
- [x] API `EXECUTION_BACKEND=simulation`.
- [x] exact username search → `found`, count 1, refinement false.
- [x] broad name search → `ambiguous`, refinement required, zero candidates/no `user_ref`.
- [x] Akamai MFA status read-only path → HTTP 200.
- [x] trusted ingress authenticated.
- [x] zero `/prepare`, `/confirm`, `/execute` calls during release smoke.

## Release evidence

- [x] Post-CS11 canonical snapshot checksum set verified.
- [x] Frozen v1 API/MCP images present and identities recorded.
- [x] Frozen v1 API/MCP/nginx Quadlets present.
- [x] Historical G4 checksum evidence revalidated unchanged.
- [x] Historical G4 snapshot and post-CS11 snapshot confirmed distinct/present.
- [x] Final MANIFEST generated.
- [x] Final documentation checksum set generated and verified.
- [x] G5 approval recorded: **PASS**.
