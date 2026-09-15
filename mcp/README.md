# Akamai MFA MCP 0.5.0-v2-dev — cumulative through Change-set 07

Source baseline: official `akamai-mfa-mcp:0.4.1`.

Transport is intentionally unchanged:

```text
Python MCP SDK 2.2.0
transport="streamable-http"
stateless_http=True
json_response=True
path=/mcp
```

## CS01 scope

The six G2-frozen public tool names/schemas are exposed so schema regressions are
caught early. Only the two read-only tools call API v2:

- `search_eaa_user`
- `get_akamai_mfa_status`

These four remain fail-closed and make no prepare/confirm/execute/retry request:

- `prepare_eaa_otp_reset`
- `reset_eaa_otp`
- `prepare_akamai_mfa_device_reset`
- `reset_akamai_mfa_device`

Destructive tools accept only `operation_id`; there is no `confirmed` argument.

## Internal API context

API v2 safe references require `X-MFA-Actor` and `X-MFA-Session`. CS05 adds a
request-bound provider for both values, while preserving the previous static
provider only as a development compatibility mode. None of these values are
model/tool inputs.

Production-candidate configuration uses LibreChat-owned request context plus a
server-controlled CS06 ingress credential:

```yaml
headers:
  X-MFA-Ingress-Token: '${MCP_TRUSTED_INGRESS_SECRET}'
  X-MFA-Actor: '{{LIBRECHAT_USER_ID}}'
  X-MFA-Session: '{{LIBRECHAT_BODY_CONVERSATIONID}}'
  X-MFA-Interaction: '{{LIBRECHAT_BODY_MESSAGEID}}'
```

`MCP_TRUSTED_CONTEXT_MODE=request_headers` now refuses to start unless CS06
`shared_secret` ingress authentication is enabled. Missing/wrong ingress
credentials fail before actor/session are accepted and before any API call.
Actor/session still fail closed when missing, empty, invalid, over bounds, or
unresolved.

## Domain language

The MCP preserves the distinction between EAA Native MFA OTP and Akamai MFA.
It does not emit the legacy generic `mfa_enabled` abstraction for v2 results and
does not recompute device eligibility.


## Change-set 02

Adds request-bound interaction attestation foundation using the MCP SDK's injected
`Context.headers`, while retaining `stateless_http=True`. Attestation is disabled
by default. All four non-read-only tools remain local fail-closed stubs and make
no backend calls.


## Change-set 02A

Probe-only hotfix: `CallToolResult.structured_content` is optional, so the
attestation validation probe now falls back to JSON-decoding model-facing
`TextContent`. Server and tool behavior are unchanged.


## Change-set 02B

Probe-only correction: the attestation probe now uses a syntactically valid,
fictitious `usr_...` reference so input validation cannot prevent the probe from
reaching the interaction-attestation gate. No backend prepare call is enabled.


## Change-set 02C

Adds development-only safe observability for interaction attestation. When
`MCP_LOG_ATTESTATION_PROBE=true`, the MCP logs a process-local keyed fingerprint
of the interaction reference, never the raw value. This allows validation that
successive human turns produce distinct interaction references before any
destructive API wiring is enabled.


## Change-set 03

Enables prepare-only API v2 wiring with request-bound interaction attestation.
Successful prepared operations are correlated to their prepared interaction in a
bounded process-local registry. Reset/confirm/execute remain fail-closed.


## Change-set 04

Adds the later-human interaction gate and controlled API `confirm → execute`
wiring for the two destructive tools. Destructive lifecycle calls are disabled
by default and require `MCP_DESTRUCTIVE_EXECUTION_MODE=enabled`. Same-turn
prepare/reset, replay, type/domain mismatch and missing correlation fail closed.
No destructive retry is automatic.


## Change-set 05

Adds request-bound trusted actor/session context. In `request_headers` mode the
MCP reads actor and session only from transport headers injected by the runtime;
static environment values are ignored. Development observability logs only
process-local keyed fingerprints and source labels, never raw actor/session values.
The public six-tool schema and CS04 lifecycle semantics are unchanged.


## Change-set 06

Authenticates the trusted LibreChat ingress with a server-controlled shared
secret before accepting request-bound actor/session/interaction headers. The
secret is not a model/tool argument and is never logged. Release-candidate
deployment also removes host publication of the MCP port as defense in depth.


## Change-set 07

Adds operational deployment hardening only: canonical dual-homed Quadlet,
explicit API-network DNS, mounted ingress secret, no host port publication,
LibreChat runtime-secret wrapper, read-only smoke probe and rollback runbooks.
Runtime tool/lifecycle logic is unchanged from CS06 and destructive execution
remains disabled by default.
