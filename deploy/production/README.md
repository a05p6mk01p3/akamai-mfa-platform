# Production deployment — Akamai MFA Platform v2

This directory defines the production promotion contract for the G5-approved release.

## Immutable OCI references

```text
API
  ghcr.io/a05p6mk01p3/akamai-mfa-api@sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af

MCP
  ghcr.io/a05p6mk01p3/akamai-mfa-mcp@sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d
```

Do not deploy production by mutable tag alone and do not rebuild this release.

## Safe default

```text
MCP_DESTRUCTIVE_EXECUTION_MODE=disabled
EXECUTION_BACKEND=simulation
```

The MCP service is dual-homed on `akamai-mfa-net` and `librechat-net`. The validated deployment uses deterministic DNS `10.89.0.1` for MCP.

## Secrets

Do not store real credentials in this repository. Production credentials must be provisioned on the target host using protected runtime configuration and/or mounted secret files. In particular, never commit Akamai client/access secrets, database credentials, trusted-ingress secrets, raw internal user/device identifiers, or unsanitized logs.

## Installation principle

On the production host:

1. authenticate to `ghcr.io` using a token with only the permissions required to pull private packages;
2. pull the two digest-pinned references above;
3. install the production Quadlets and environment/secret files with local permissions appropriate to the host;
4. keep destructive execution disabled for the initial go-live;
5. run readiness and read-only smoke tests;
6. roll back to the frozen v1 line if the agreed rollback trigger is met.

The exact host-specific Quadlets and environment files must be derived from the validated deployment and reviewed before cutover. Do not copy development hostnames or validation-only settings from historical source examples into production.

See `release/IMAGE-IDENTITY.md` for image provenance and `docs/OPERATIONS-AND-ROLLBACK.md` for operational constraints.
