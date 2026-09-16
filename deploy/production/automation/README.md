# Production automation installer

This directory adds fail-closed automation around the reviewed `deploy/production` bundle. It does not rebuild or modify API 0.8.0 or MCP 0.5.0 and it never enables destructive execution.

## Scope

The automation targets a **new/clean host**. Two explicit host profiles are available:

- `validated-ol8.10` (default): Oracle Linux 8.10, systemd 239, Podman 4.9.4-rhel, Quadlet, SELinux Enforcing;
- `corporate-rhel8.7`: RHEL 8.7, systemd 239, Podman 4.9.4-rhel, Quadlet, SELinux Disabled. This profile exists to reproduce the supplied corporate Linux baseline and remains qualification evidence until a clean-host rehearsal completes successfully.

Both profiles require a synchronized system clock, at least 5 GiB free on the container-storage filesystem, PostgreSQL/API/MCP on the same host, and the same frozen digest-pinned images. MCP remains dual-homed on `akamai-mfa-net` and `librechat-net`; LibreChat itself is managed separately and uses `librechat-net` to reach MCP.

Deploying onto an already-active v2 host is refused. The historical v1 rollback process is also not synthesized here; `rollback.sh` is a clean-install **safe stop** that preserves data, secrets, images and configuration for diagnosis.

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

For the validated Oracle Linux profile:

```sh
sudo sh deploy/production/automation/deploy-production.sh \
  --check-only \
  --config /etc/akamai-mfa/production.conf \
  --secrets-dir /run/akamai-mfa-secrets \
  --authfile /run/containers/0/auth.json
```

For the supplied corporate RHEL 8.7 baseline, add:

```text
--host-profile corporate-rhel8.7
```

`--check-only` does not pull images, write environment files, create secrets, install Quadlets, start services or apply a database migration. It validates the selected host profile, configuration file, repository identity, secret readiness and any already-present image identity.

Expected terminal gate:

```text
CHECK_ONLY=PASS
```

`--allow-platform-drift` exists only for an explicitly approved compatibility test and should not replace a named host profile. `--skip-network-check` similarly requires an explicit operational reason.

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

Add `--host-profile corporate-rhel8.7` when using the supplied corporate rehearsal baseline.

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

Quadlet-generated systemd services are generated/transient units and must not be passed to `systemctl enable`. Boot persistence comes from `WantedBy=multi-user.target` in the three container Quadlets; the Quadlet generator materializes that wiring at boot and on daemon-reload. The automation therefore uses `systemctl start` for runtime activation.

If `--approve-start` is omitted, the automation stops after `PREFLIGHT=PASS`, masks PostgreSQL/API/MCP so the staged state remains stopped across a reboot, and returns `STAGED_SAFE_STOP=PASS` plus `DEPLOYMENT=READY_TO_START`. To continue a staged deployment, rerun with `--approve-start --reuse-existing-secrets`; the orchestrator unmasks the three application/database units immediately before final preflight/start and arms rollback before doing so.

## Database bootstrap

`bootstrap-db.sh` applies only `api/migrations/001_v2_repository.sql`. It is idempotent when all three expected tables already exist. It fails closed if only part of the schema exists so a human can inspect a partial migration instead of silently guessing how to repair it.

The script never drops a table, database or volume.

## Failure handling

After final start approval is armed, any orchestrator failure invokes `rollback.sh`. The clean-host rollback stops and **masks** MCP, API and PostgreSQL in reverse dependency order, preserving the mask across reboot while leaving PostgreSQL data, Podman secrets, pulled images, generated runtime env files, installed Quadlets and networks intact for diagnosis.

Masking is intentional: generated Quadlet services cannot be persistently disabled with `systemctl disable` because their `[Install]` wiring is regenerated. A later approved deployment removes those masks before startup.

For an established deployment, use the separately documented operational rollback procedure rather than this clean-host installer.
