# CS07 deployment runbook

This runbook is intentionally secret-safe. Never print the ingress token and do
not use a full `podman inspect` environment dump.

## 1. Snapshot before cutover

Create a root-only timestamped directory and copy the current source Quadlets,
LibreChat YAML, wrapper and MCP non-secret env file if present. Preserve the
frozen v1 deployment separately. Do not add these VM snapshots back into the
project artifact.

Record image identity using narrowly scoped commands such as:

```bash
sudo podman image inspect localhost/akamai-mfa-mcp:0.5.0-v2-dev-cs07 \
  --format 'id={{.Id}} digest={{.Digest}}'
```

## 2. Install canonical MCP files

- `/etc/containers/systemd/akamai-mfa-mcp-v2.container`
- `/opt/akamai-mfa/config/akamai-mfa-mcp-v2.env` mode `0640` or stricter
- Podman secret named `akamai-mfa-mcp-ingress-token`

On the observed Podman 4.9.4 host, edit/copy the source `.container` directly;
do not depend on `*.container.d` source drop-ins.

After `systemctl daemon-reload`, inspect generated `ExecStart` and verify:

- two `--network` attachments;
- `--dns 10.89.0.1`;
- `--secret akamai-mfa-mcp-ingress-token...`;
- no `-p`, `--publish`, or host port mapping.

## 3. Validate MCP before LibreChat cutover

Verify:

```text
akamai-mfa-net + librechat-net
/etc/resolv.conf -> nameserver 10.89.0.1
API hostname resolves
LibreChat resolves akamai-mfa-mcp-v2
podman port akamai-mfa-mcp-v2 -> empty
```

Run `scripts/cs07_readonly_smoke.py --query <sanitized-test-query>` inside the
container. It must make only the read-only EAA search call.

## 4. LibreChat cutover

LibreChat must mount the SAME Podman secret as a file and export it only at
runtime through `librechat-cs07-entrypoint.sh`. The secret value must not appear
in `librechat.yaml`, `librechat.env`, Quadlet `Environment=`, or `.Config.Env`.

Update only the v2 MCP server entry/allowlist to the canonical hostname
`akamai-mfa-mcp-v2:9000`. Keep the frozen v1 server untouched.

## 5. Acceptance evidence

Required evidence:

```text
trusted_ingress authenticated=True
trusted_context actor_source=request_header
interaction_attestation present=True
GET /v2/eaa/users/search ... 200
```

During this smoke test there must be zero `/prepare`, `/confirm`, `/execute` and
zero destructive upstream request.
