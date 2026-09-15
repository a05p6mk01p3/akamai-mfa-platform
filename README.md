# Akamai MFA Platform

Private production repository for the Akamai MFA Platform release line.

## Frozen release

- API: `0.8.0`
- MCP: `0.5.0`
- Git release line: `v2.0.0`
- Final gate: `G5 PASS`

The validated production-safe default is:

```text
MCP_DESTRUCTIVE_EXECUTION_MODE=disabled
EXECUTION_BACKEND=simulation
```

Production deployment must use OCI images pinned by digest. Do not rebuild the G5-approved images when promoting this release; publish/promote the already-approved OCI blobs instead.

## Repository layout

```text
api/        frozen API 0.8.0 source
mcp/        frozen MCP 0.5.0 source
deploy/     sanitized deployment templates
docs/       frozen release documentation
release/    release identity and checksums
```

## Security

Do not commit real `.env` files, credentials, Akamai tokens, database passwords, trusted-ingress secrets, raw user/device identifiers, VM backups, or unsanitized logs.

See `docs/OPERATIONS-AND-ROLLBACK.md` and `docs/G5-RELEASE-CHECKLIST.md` for the approved operational state and release evidence.
