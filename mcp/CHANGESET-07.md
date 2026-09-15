# Change-set 07 — operational deployment hardening

CS07 does not change the six-tool public contract or destructive lifecycle logic.
It turns the CS06 security/runtime behavior into a reproducible Podman/Quadlet
candidate deployment for G3 implementation freeze and later G4 RC promotion.

## Deployment invariants

The MCP v2 candidate MUST:

- run without a host-published MCP port;
- join both `akamai-mfa-net` and `librechat-net`;
- use explicit DNS `10.89.0.1` so API service discovery is deterministic;
- authenticate LibreChat ingress with a Podman secret mounted as a file;
- keep actor/session/interaction request-bound and model-invisible;
- keep `MCP_DESTRUCTIVE_EXECUTION_MODE=disabled` by default;
- use a deterministic container/service name rather than a changeset test name;
- preserve the frozen v1 deployment for rollback.

The observed Oracle Linux runtime uses Podman 4.9.4. On that runtime source
Quadlet drop-ins (`*.container.d/*.conf`) were not incorporated by the generator.
CS07 therefore treats the source `.container` file as the canonical deployment
unit and requires an explicit backup before editing it.

## Canonical candidate names

Development candidate:

```text
image:     localhost/akamai-mfa-mcp:0.5.0-v2-dev-cs07
container: akamai-mfa-mcp-v2
service:   akamai-mfa-mcp-v2.service
secret:    akamai-mfa-mcp-ingress-token
```

The image tag is a convenience label only. Before RC promotion, record and pin
the immutable image digest/ID used by the accepted candidate.

## Files added in CS07

- `deploy/akamai-mfa-mcp-v2.container.example`
- `deploy/akamai-mfa-mcp-v2.env.example`
- `deploy/librechat-cs07-entrypoint.sh`
- `deploy/librechat-mcp-v2.yaml.snippet`
- `deploy/CS07-DEPLOY-RUNBOOK.md`
- `deploy/CS07-ROLLBACK-RUNBOOK.md`
- `scripts/cs07_readonly_smoke.py`
- `tests/test_cs07_deploy_static.py`

No real credential, token, password, internal destructive identifier or tenant
secret is present in these files.

## Promotion gates

### CS07-A — artifact/build integrity

- full unit/static suite passes;
- image builds as `0.5.0-v2-dev-cs07`;
- image ID/digest is recorded;
- frozen v1 image remains present.

### CS07-B — canonical MCP Quadlet

- `akamai-mfa-mcp-v2.service` is generated from the source Quadlet;
- no `PublishPort=` or CLI `-p/--publish` exists;
- both required networks are attached;
- `/etc/resolv.conf` uses `10.89.0.1` deterministically;
- ingress secret is readable only as a mounted secret file;
- `.Config.Env` does not contain the ingress secret;
- destructive execution is disabled.

### CS07-C — LibreChat read-only cutover

- LibreChat resolves `akamai-mfa-mcp-v2` on `librechat-net`;
- ingress authentication succeeds;
- actor/session/interaction remain request-bound;
- a read-only EAA search reaches API v2 with HTTP 200;
- no prepare/confirm/execute occurs in the cutover smoke test.

### CS07-D — operational rollback rehearsal

- pre-cutover Quadlet/YAML/wrapper snapshots exist;
- LibreChat can be pointed back to the previously accepted MCP endpoint;
- the canonical v2 candidate can be stopped without modifying frozen v1;
- rollback does not require revealing or copying secret values into YAML/env;
- restore steps are timed and recorded for the later G4 full-platform rehearsal.

CS07 is not permission to enable destructive execution. That remains an explicit,
separate promotion decision after implementation/security freeze.
