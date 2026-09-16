# Production automation installer

This directory adds fail-closed automation around the reviewed `deploy/production` bundle. It does not rebuild or modify API 0.8.0 or MCP 0.5.0 and it never enables destructive execution.

## Scope

The automation targets a **new/clean host** using the validated production topology:

- Oracle Linux 8.10 baseline;
- systemd 239;
- Podman 4.9.4-rhel with Quadlet;
- SELinux enforcing;
- synchronized system clock;
- PostgreSQL, API and MCP on the same host;
- MCP dual-homed on `akamai-mfa-net` and `librechat-net`;
- LibreChat itself is managed separately and uses `librechat-net` to reach MCP.

Deploying onto an already-active v2 host is refused. The historical v1 rollback process is also not synthesized here; `rollback.sh` is a clean-install **safe stop** that preserves data, secrets, images and configuration for diagnosis.

## Files

```text
automation/
├── common.sh
├── host-preflight.sh
├── pull-images.sh
├── render-env.sh
├── provision-secrets.sh
├── bootstrap-db.sh
├── rollback.sh
├── deploy-production.sh
├── production.conf.example
└── README.md
```

## Security model

No secret value is accepted in `production.conf` or on the command line. Required Podman secrets are read from protected files or may already exist in Podman. Secret source files must be regular, non-symlink files owned by `root:root` with mode `0400`, `0600` or `0640`.

The six expected source filenames are exactly the Podman secret names:

```text
akamai-mfa-pg-v2-password
akamai-mfa-api-v2-client-token
akamai-mfa-api-v2-client-secret
akamai-mfa-api-v2-access-token
akamai-mfa-api-v2-database-url
akamai-mfa-mcp-ingress-token
```

A typical temporary secret directory is `/run/akamai-mfa-secrets`. A corporate secret manager or tmpfs-backed delivery mechanism is preferred. The automation never prints secret contents.

GHCR authentication is external to the installer. Either pre-authenticate root Podman or pass a protected Podman authfile with `--authfile FILE`. The installer never accepts a registry token as an argument.

## Prepare configuration

Copy the example and fill all non-secret values from the approved production configuration:

```sh
sudo install -d -o root -g root -m 0700 /etc/akamai-mfa
sudo install -o root -g root -m 0600 \
  deploy/production/automation/production.conf.example \
  /etc/akamai-mfa/production.conf
sudoedit /etc/akamai-mfa/production.conf
```

`EXPECTED_REPO_COMMIT` must be the exact approved commit checked out on the target host. This prevents silently deploying a later `main` revision.

The two safety controls are not configurable. Generated runtime files always contain:

```text
EXECUTION_BACKEND=simulation
MCP_DESTRUCTIVE_EXECUTION_MODE=disabled
```

## Non-mutating validation

Run this before the change window:

```sh
sudo sh deploy/production/automation/deploy-production.sh \
  --check-only \
  --config /etc/akamai-mfa/production.conf \
  --secrets-dir /run/akamai-mfa-secrets \
  --authfile /run/containers/0/auth.json
```

`--check-only` does not pull images, write environment files, create secrets, install Quadlets, start services or apply a database migration. It validates the host baseline, configuration file, repository identity, secret readiness and any already-present image identity.

Expected terminal gate:

```text
CHECK_ONLY=PASS
```

`--allow-platform-drift` exists only for an explicitly approved compatibility test. It should not be used to bypass production qualification. `--skip-network-check` similarly requires an explicit operational reason.

## Automated deployment

One-command deployment with explicit start approval:

```sh
sudo sh deploy/production/automation/deploy-production.sh \
  --deploy \
  --approve-start \
  --config /etc/akamai-mfa/production.conf \
  --secrets-dir /run/akamai-mfa-secrets \
  --authfile /run/containers/0/auth.json
```

The flow is:

```text
host preflight
  -> repository/config/secret validation
  -> immutable image pull + ID/digest verification
  -> static production bundle installation
  -> fail-closed runtime env rendering
  -> Podman secret provisioning
  -> production preflight
  -> explicit start gate
  -> networks + PostgreSQL
  -> PostgreSQL readiness
  -> idempotent schema bootstrap
  -> API start + readiness
  -> MCP start + readiness
  -> non-destructive smoke
  -> runtime image ID verification
```

Expected terminal gate:

```text
DEPLOYMENT=PASS
```

If `--approve-start` is omitted, the automation stops after `PREFLIGHT=PASS` with `DEPLOYMENT=READY_TO_START`. To continue a staged deployment, rerun with `--approve-start --reuse-existing-secrets`.

## Database bootstrap

`bootstrap-db.sh` applies only `api/migrations/001_v2_repository.sql`. It is idempotent when all three expected tables already exist. It fails closed if only part of the schema exists so a human can inspect a partial migration instead of silently guessing how to repair it.

The script never drops a table, database or volume.

## Failure handling

After service startup begins, any orchestrator failure invokes `rollback.sh`, which stops and disables MCP, API and PostgreSQL in reverse dependency order. It deliberately preserves:

- PostgreSQL volume/data;
- Podman secrets;
- pulled images;
- generated runtime env files;
- installed Quadlets and networks.

That preservation makes incident evidence available and avoids destructive rollback behavior. For an established deployment, use the separately documented operational rollback procedure rather than this clean-host installer.
