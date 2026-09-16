# Akamai MFA Platform v2 — Final Release Notes

**Release date:** 2026-09-15  
**Status:** RELEASED — G5 PASS  
**API:** `0.8.0`  
**MCP:** `0.5.0`

## Summary

Akamai MFA Platform v2 is released after functional/architecture freeze, cumulative API/MCP regression, canonical Podman/Quadlet deployment, cold-start/reboot validation, rehearsed rollback to frozen v1, bounded EAA-search refinement, controlled real Akamai MFA destructive tenant validation, an expired-operation diagnostic fix, source/image freeze and final read-only release smoke.

## Final images

```text
API tag:      localhost/akamai-mfa-api:0.8.0
API image ID: 650a0e1b1dedb1f696cc34feac334c5fb9da59a2d8fcabf3a348f50e19814512
API digest:   sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af

MCP tag:      localhost/akamai-mfa-mcp:0.5.0
MCP image ID: d865a90ea546edcf7df039b2007e1f31528acc174d98fec513d957e15264d213
MCP digest:   sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d
```

Final tags reference the approved canonical image IDs without rebuild.

## Final regression

```text
API unit suite: 90/90 PASS
MCP suite:      109/109 PASS
```

## Functional and safety highlights

- six frozen public MCP tools;
- strict EAA Native MFA vs Akamai MFA domain separation;
- `q` accepts username, sAMAccountName or name;
- exact identifier wins;
- >5/has-more broad search requires refinement and returns zero candidates/references;
- backend owns destructive targets;
- Akamai MFA reset eligibility is deny-by-default;
- later trusted human interaction is required after prepare;
- no public `confirmed=true`;
- no blind destructive retry;
- mandatory post-check;
- expired prepared operations fail closed and, when locally known, return `prepared_operation_expired`;
- trusted ingress and request-bound actor/session/interaction context remain runtime-owned.

## CS11 tenant validation

One dedicated Akamai MFA device reset completed with exactly one prepare, one confirm and one execute, no automatic destructive retry, target-absent post-check and independent tenant verification showing the account preserved with zero eligible factors afterward. Canonical destructive mode was disabled again and API execution backend returned to simulation.

## Final G5 smoke

All canonical services active; API `/ready` 200; exact search found one identity; broad search required refinement with zero candidate refs; Akamai MFA status returned 200; trusted ingress authenticated; zero destructive lifecycle POSTs occurred during release smoke.

## Source artifacts

```text
API source bundle SHA-256: 09e83207c0f4bb3368d2968c71c4c48b2ea5d8375263f2c2a84ee3b5f9e8b668
MCP source bundle SHA-256: 65a9a932b969c1ecf23391a9eef37b0b693fee905d0bf263adfc23114705f0a4
```

Both bundles are cache-clean and match their approved source trees.

## Rollback

Frozen v1 API `0.7.1` / MCP `0.4.1` remain present. Historical G4 evidence validated unchanged; full rollback rehearsal result remains 8 seconds (<300 s). The final current snapshot is `/opt/akamai-mfa/backups/post-cs11-canonical`.

## Default deployment safety state

```text
MCP_DESTRUCTIVE_EXECUTION_MODE=disabled
EXECUTION_BACKEND=simulation
```
