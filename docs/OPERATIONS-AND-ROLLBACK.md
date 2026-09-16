# Akamai MFA Platform v2 — Final Operations and Rollback Notes

**Status:** FINAL — G5 PASS  
**Date:** 2026-09-15

## Canonical release state

- API final tag `localhost/akamai-mfa-api:0.8.0`, runtime digest `sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af`.
- MCP final tag `localhost/akamai-mfa-mcp:0.5.0`, runtime digest `sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d`.
- Quadlets remain digest-pinned.
- `MCP_DESTRUCTIVE_EXECUTION_MODE=disabled`.
- API `EXECUTION_BACKEND=simulation`.
- MCP is dual-homed on `akamai-mfa-net` and `librechat-net`, with deterministic DNS `10.89.0.1`.

## Safe operator rules

1. Use `q` for EAA identity search.
2. Exact username/sAMAccountName resolves one identity.
3. If a broad query has more than five matches, require refinement and expose no candidate reference.
4. Never supply or request raw internal Akamai IDs.
5. Never combine prepare and destructive execution into the same human interaction.
6. Never blindly retry destructive POST/DELETE after transport uncertainty.
7. Never substitute an EAA OTP reset for an Akamai MFA device reset, or vice versa.
8. An expired prepared operation must be prepared again; `prepared_operation_expired` is fail-closed.

## Destructive execution

G5 release approval does not leave destructive execution enabled. CS11 proved the real path only in a controlled temporary validation window. Any future enablement requires an explicit change window, pre/post evidence and immediate restoration to the configured safe state unless a separately approved production policy says otherwise.

## Canonical snapshot

Current release snapshot:

```text
/opt/akamai-mfa/backups/post-cs11-canonical
```

Its checksum set was validated during G5.

## Rollback target

Frozen v1 remains the rollback target:

```text
API 0.7.1
  image ID: e041083f014ebc180f6d85dc719c842535beae9d89cfb3da97e2c5fb779948fd
  digest:   sha256:2395e0191fbdcfbadb894b3317a20cc575949c09d942f65b27b82d514132c156

MCP 0.4.1
  image ID: d37eb7b0344dc704cccaa36e437ed30f1b8cbe321a972e4ff8d64852972ad6a5
  digest:   sha256:5c8000c3483e4f4986dc6a0024f8d0a5ae20437e63477ac953b7059f648d05b3
```

The v1 API/MCP/nginx Quadlets were confirmed present during G5. The only documented v1 deployment hardening is deterministic DNS for MCP; v1 code/images/contracts remain frozen.

## Historical G4 evidence

Do not overwrite or reinterpret:

```text
/opt/akamai-mfa/backups/g4-rollback-rehearsal/v2-restore
```

The historical `SHA256SUMS` validated successfully during G5. It records the v2 state used in the original rollback rehearsal and is not the current post-CS11 restore snapshot.

The rehearsed full-platform rollback to frozen v1 completed in 8 seconds, below the 300-second gate, with functional v1 smoke and subsequent v2 restoration.
