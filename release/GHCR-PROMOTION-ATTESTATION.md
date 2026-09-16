# GHCR Promotion Attestation

**Attestation date:** 2026-09-16  
**Release tag:** `v2.0.0` (unchanged)  
**Published source commit:** `03110df03a3f127ab1be758c18ccc91820a6f335`  
**Release status:** G5 PASS

This document records the observed promotion and runtime cutover evidence for the frozen Akamai MFA Platform v2 release. It does not authorize a rebuild, source change, or destructive-mode enablement.

## Approved image identities

### API 0.8.0

- Approved image ID: `650a0e1b1dedb1f696cc34feac334c5fb9da59a2d8fcabf3a348f50e19814512`
- Approved/published digest: `sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af`
- Production reference: `ghcr.io/a05p6mk01p3/akamai-mfa-api@sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af`

### MCP 0.5.0

- Approved image ID: `d865a90ea546edcf7df039b2007e1f31528acc174d98fec513d957e15264d213`
- Approved/published digest: `sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d`
- Production reference: `ghcr.io/a05p6mk01p3/akamai-mfa-mcp@sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d`

## Promotion evidence

The G5-approved API and MCP images were promoted to GHCR without rebuild and with digest preservation. A subsequent digest-pinned pull-back on the deployment host produced the exact approved image IDs and digests for both components:

```text
API local approved ID == GHCR pull-back ID
API local approved digest == GHCR pull-back digest

MCP local approved ID == GHCR pull-back ID
MCP local approved digest == GHCR pull-back digest
```

Observed result:

```text
GHCR_API_PROMOTION=PASS
GHCR_MCP_PROMOTION=PASS
NO_REBUILD=PASS
IMAGE_IDENTITY_PULLBACK=PASS
```

## Source archive path-safety gate

The frozen source archives were inspected for absolute paths and parent-directory traversal entries before publication closure.

```text
akamai-mfa-api-0.8.0-source.tar.gz UNSAFE_PATHS=0
akamai-mfa-mcp-0.5.0-source.tar.gz UNSAFE_PATHS=0
```

Observed result:

```text
SOURCE_ARCHIVE_PATH_SAFETY=PASS
```

## In-place runtime cutover

Before restart, the current API and MCP Quadlets were backed up and their checksums verified. The deployment Quadlets were changed only in their `Image=` reference, from the approved local digest-pinned names to the corresponding GHCR digest-pinned names. Normalized byte-for-byte comparison confirmed no other Quadlet content changed.

Observed result:

```text
QUADLET_BACKUP_INTEGRITY=PASS
API_ONLY_IMAGE_REF_CHANGED=PASS
MCP_ONLY_IMAGE_REF_CHANGED=PASS
PRODUCTION_PREFLIGHT=PASS
```

The API was restarted first and passed readiness before the MCP restart. The MCP was then restarted and passed readiness. PostgreSQL was not recreated, its data volume was not replaced, and LibreChat remained active through the cutover.

Final runtime identity matched the approved images:

```text
API_ID=650a0e1b1dedb1f696cc34feac334c5fb9da59a2d8fcabf3a348f50e19814512
API_REF=ghcr.io/a05p6mk01p3/akamai-mfa-api@sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af

MCP_ID=d865a90ea546edcf7df039b2007e1f31528acc174d98fec513d957e15264d213
MCP_REF=ghcr.io/a05p6mk01p3/akamai-mfa-mcp@sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d
```

## Final safe state and smoke

The production-safe release state remained enforced after cutover:

```text
EXECUTION_BACKEND=simulation
MCP_DESTRUCTIVE_EXECUTION_MODE=disabled
```

The final non-destructive smoke completed with:

```text
POSTGRES_V2_READY=PASS
API_V2_READY=PASS
MCP_V2_READY=PASS
SAFE_STATE=PASS
SMOKE=PASS
```

## Attested chain

```text
frozen source
  -> G5-approved local image
  -> digest-preserving GHCR promotion
  -> digest-pinned GHCR pull-back
  -> identical image ID and digest
  -> image-reference-only Quadlet cutover
  -> API readiness
  -> MCP readiness
  -> safe-state smoke PASS
```

The `v2.0.0` tag remains the frozen application release snapshot. This attestation is additive publication evidence only and does not move or rewrite that tag.
