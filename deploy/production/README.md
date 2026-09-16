# Production deployment — Akamai MFA Platform v2

This directory contains the reviewed installation bundle derived from the G5-approved deployment. It does not change the frozen application source or rebuild either release image.

## Immutable OCI references

```text
API
  ghcr.io/a05p6mk01p3/akamai-mfa-api@sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af

MCP
  ghcr.io/a05p6mk01p3/akamai-mfa-mcp@sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d

PostgreSQL
  docker.io/library/postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2
```

Do not deploy API or MCP by mutable tag alone and do not rebuild this release.

## Canonical initial safe state

```text
MCP_DESTRUCTIVE_EXECUTION_MODE=disabled
EXECUTION_BACKEND=simulation
```

The initial production cutover must retain that state. Permanent destructive enablement is a separate operational gate and is not authorized by this bundle.

## Layout

```text
production/
├── automation/
│   ├── deploy-production.sh
│   ├── host-preflight.sh
│   ├── pull-images.sh
│   ├── render-env.sh
│   ├── provision-secrets.sh
│   ├── bootstrap-db.sh
│   ├── rollback.sh
│   ├── common.sh
│   ├── production.conf.example
│   └── README.md
├── quadlets/
│   ├── akamai-mfa-postgres-v2.container
│   ├── akamai-mfa-api-v2.container
│   └── akamai-mfa-mcp-v2.container
├── networks/
│   ├── akamai-mfa.network
│   └── librechat.network
├── bin/
│   ├── akamai-mfa-api-v2-entrypoint.sh
│   ├── wait-postgres-v2-ready.sh
│   ├── wait-api-v2-ready.sh
│   └── wait-mcp-v2-ready.sh
├── env/
│   ├── postgres-v2.env.example
│   ├── api-v2.env.example
│   └── mcp-v2.env.example
├── install.sh
├── preflight.sh
├── smoke.sh
└── README.md
```

For a new corporate host, prefer `automation/deploy-production.sh`. The manual procedure below remains the reference for inspecting each deployment stage.

## Network contract

- PostgreSQL: `akamai-mfa-net` only.
- API: `akamai-mfa-net` only, DNS `10.89.0.1`.
- MCP: dual-homed on `akamai-mfa-net` and `librechat-net`, DNS `10.89.0.1`.
- LibreChat itself uses `librechat.network`; MCP is the dual-homed component that provides the network path from LibreChat to the Akamai MFA API.
- The LibreChat deployment remains responsible for its own application configuration and for injecting the same trusted-ingress secret into its runtime.

If the production LibreChat installation already owns `/etc/containers/systemd/librechat.network`, it must be reviewed for equivalence before using this bundle. `install.sh` refuses to overwrite a differing existing file.

## Automated clean-host deployment

See `automation/README.md`. The non-mutating gate is:

```sh
sudo sh automation/deploy-production.sh \
  --check-only \
  --config /etc/akamai-mfa/production.conf \
  --secrets-dir /run/akamai-mfa-secrets \
  --authfile /run/containers/0/auth.json
```

The deployment command is:

```sh
sudo sh automation/deploy-production.sh \
  --deploy \
  --approve-start \
  --config /etc/akamai-mfa/production.conf \
  --secrets-dir /run/akamai-mfa-secrets \
  --authfile /run/containers/0/auth.json
```

The automation is intentionally limited to a new/clean host and refuses an already-active v2 deployment.

## Manual procedure

### 1. Authenticate and pull immutable images

Authenticate locally to the private GHCR packages using a pull-only credential. Never paste the token into documentation, shell history, or issue/PR text.

Then pull the immutable references:

```sh
podman pull ghcr.io/a05p6mk01p3/akamai-mfa-api@sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af
podman pull ghcr.io/a05p6mk01p3/akamai-mfa-mcp@sha256:07e5fa0d6a717b490360ee703a45bfca4bce971df54047d775ae8a7d9a9e484d
podman pull docker.io/library/postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2
```

Run these as the same user context that will run the system Quadlets (root for the validated deployment).

### 2. Install static deployment files

From this directory:

```sh
sudo sh ./install.sh
```

The installer:

- installs the three container Quadlets and two network Quadlets;
- installs the API wrapper and readiness helpers;
- copies only `.env.example` files;
- never creates live credentials or live environment files;
- refuses to overwrite a differing existing deployment file;
- does not start containers.

### 3. Create live environment files locally

Copy each example to its live path and replace every `CHANGE_ME` using the approved production values:

```text
/opt/akamai-mfa/config/postgres-v2/postgres-v2.env
/opt/akamai-mfa/config/api-v2/api-v2.env
/opt/akamai-mfa/config/mcp-v2/mcp-v2.env
```

Set ownership to `root:root`. Supported modes are `0600`, `0640`, or `0400`; when `0640` is used, the group must remain `root`. Do not put Akamai tokens, database credentials, or the trusted-ingress token in these files.

All deployment-specific non-secret values are intentionally `CHANGE_ME` in the examples unless they are part of the frozen safe-state contract or a fixed Podman secret path. Copy approved values rather than inferring defaults.

### 4. Provision Podman secrets

The deployment requires these secret names:

```text
akamai-mfa-pg-v2-password
akamai-mfa-api-v2-client-token
akamai-mfa-api-v2-client-secret
akamai-mfa-api-v2-access-token
akamai-mfa-api-v2-database-url
akamai-mfa-mcp-ingress-token
```

Create them locally from protected input/stdin. Never pass secret values as command-line arguments and never commit them.

The PostgreSQL environment points `POSTGRES_PASSWORD_FILE` at `/run/secrets/pg_password`. The API wrapper reads its four required secret files under `/run/secrets`. MCP reads its trusted-ingress credential from `/run/secrets/akamai-mfa-mcp-ingress-token`.

### 5. Run preflight

After images, live env files, and secrets are provisioned:

```sh
sudo sh ./preflight.sh
```

Expected terminal gate:

```text
PREFLIGHT=PASS
```

The preflight does not start application containers. It checks safe-state configuration, required secret objects, exact digest-pinned images, installed files, and generated systemd units.

### 6. Start networks and PostgreSQL, then bootstrap the clean database

```sh
sudo systemctl enable --now akamai-mfa-network.service
sudo systemctl enable --now librechat-network.service
sudo systemctl enable --now akamai-mfa-postgres-v2.service
sudo /opt/akamai-mfa/bin/wait-postgres-v2-ready.sh
```

On a new database, apply the frozen v2 repository migration before starting the API:

```sh
cat ../../api/migrations/001_v2_repository.sql | \
  sudo podman exec -i akamai-mfa-postgres-v2 \
    sh -lc 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

The automated installer performs this step through `automation/bootstrap-db.sh` and fails closed if it detects a partial schema.

### 7. Start API and MCP in dependency order

```sh
sudo systemctl enable --now akamai-mfa-api-v2.service
sudo /opt/akamai-mfa/bin/wait-api-v2-ready.sh
sudo systemctl enable --now akamai-mfa-mcp-v2.service
sudo /opt/akamai-mfa/bin/wait-mcp-v2-ready.sh
```

If `librechat-network.service` is already enabled by the existing LibreChat deployment, do not replace or recreate its network; verify it and continue.

### 8. Non-destructive smoke

```sh
sudo sh ./smoke.sh
```

Expected final output:

```text
SAFE_STATE=PASS
SMOKE=PASS
```

This smoke checks service/readiness state and verifies `EXECUTION_BACKEND=simulation` plus `MCP_DESTRUCTIVE_EXECUTION_MODE=disabled`. It does not perform a destructive request and does not query a real user identity.

## LibreChat integration

The validated topology has LibreChat on `librechat.network` only. MCP is dual-homed on `librechat-net` and `akamai-mfa-net`, depends on the API, and provides the network bridge between the LibreChat side and the API side. LibreChat depends on MCP and mounts the same trusted-ingress secret. LibreChat-specific Quadlet/YAML files are deliberately not synthesized in this bundle because their complete production image/config identity was not part of the supplied G5 publication data. Preserve the already-reviewed LibreChat deployment or review its production artifacts separately before cutover.

## Rollback

Do not overwrite or delete the frozen v1 assets. The historical G4 rehearsal demonstrated rollback within the release target. Use `docs/OPERATIONS-AND-ROLLBACK.md` for rollback triggers and the preserved v1 image/Quadlet identities.

For a new clean host, `automation/rollback.sh` is deliberately narrower: it safe-stops the newly started v2 PostgreSQL/API/MCP services and preserves data and configuration for diagnosis. It is not a substitute for the historical v1 rollback procedure.

## Provenance

See `release/IMAGE-IDENTITY.md` and `release/GHCR-PROMOTION-ATTESTATION.md` for publication identity/evidence and `docs/G5-RELEASE-CHECKLIST.md` for release evidence. The `v2.0.0` tag remains the frozen application release; this production bundle is an operational deployment addition and must not rewrite that tag.
