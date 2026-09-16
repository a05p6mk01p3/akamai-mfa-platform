# Akamai MFA Platform v2 — Published Image Identity

**Publication date:** 2026-09-15  
**Source commit:** `03110df03a3f127ab1be758c18ccc91820a6f335`  
**Release status:** G5 PASS

## API

- Component version: `0.8.0`
- GHCR tag: `ghcr.io/a05p6mk01p3/akamai-mfa-api:0.8.0`
- Approved image ID: `650a0e1b1dedb1f696cc34feac334c5fb9da59a2d8fcabf3a348f50e19814512`
- Approved/published digest: `sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af`
- Production reference: `ghcr.io/a05p6mk01p3/akamai-mfa-api@sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af`

## MCP

- Component version: `0.5.0`
- GHCR tag: `ghcr.io/a05p6mk01p3/akamai-mfa-mcp:0.5.0`
- Approved image ID: `d865a90ea546edcf7df039b2007e1f31528acc174d98fec513d957e15264d213`
- Approved/published digest: `sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d`
- Production reference: `ghcr.io/a05p6mk01p3/akamai-mfa-mcp@sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d`

## Promotion rule

These GHCR objects were promoted from the G5-approved local images without rebuild and were verified to retain the exact approved digests. Production deployments must use the digest-pinned references above rather than mutable tags.

## Canonical safe state

```text
MCP_DESTRUCTIVE_EXECUTION_MODE=disabled
EXECUTION_BACKEND=simulation
```
