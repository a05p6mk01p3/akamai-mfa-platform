# CHANGESET-04 — Later-human gate + API confirm → execute

Target: `akamai-mfa-mcp 0.5.0-v2-dev`

## Scope

CS04 wires the two destructive public tools to the API operation lifecycle while
preserving the frozen six-tool contract:

```text
reset_eaa_otp(operation_id)
reset_akamai_mfa_device(operation_id)
```

For a valid later-human invocation, MCP performs exactly:

```text
POST /v2/operations/{operation_id}/confirm
        ↓ success only
POST /v2/operations/{operation_id}/execute
```

No target/device reference is sent to execute.

## MCP preconditions

Before any confirm call, the process-local trusted registry must establish:

```text
same actor/session
current interaction != prepared interaction
expected operation type/domain
local operation claim not already consumed
```

Same-interaction prepare → reset is rejected before the API.

## Explicit execution switch

CS04 defaults to fail-closed:

```text
MCP_DESTRUCTIVE_EXECUTION_MODE=disabled
```

To exercise confirm/execute in a controlled test environment, an operator must
explicitly set:

```text
MCP_DESTRUCTIVE_EXECUTION_MODE=enabled
```

This switch is deployment-owned and is not a tool/model argument.

## No blind retry

- confirm is never automatically retried;
- execute is never automatically retried;
- transport uncertainty triggers at most one observational GET of the operation;
- an execute transport ambiguity never causes a second execute;
- no child retry is prepared automatically;
- `REQUIRES_RECONFIRMATION` is returned to the operator for a later explicit
  retry-prepare request.

## Output safety

Execution output is whitelisted. `post_check_result` is intentionally not
forwarded by MCP CS04, preventing accidental leakage of future/internal fields.
The API `status` and safe `outcome_code` remain authoritative.

## Process restart behavior

The prepared-interaction registry remains process-local. After MCP restart,
operations prepared by the prior process fail closed at the MCP boundary. The
API remains the persistent lifecycle authority.

## Known development limitation

`MCP_API_ACTOR` and `MCP_API_SESSION` are still deployment-static in this dev
changeset. This is acceptable only for controlled single-operator validation;
production/multi-user rollout requires trusted request-bound actor/session
context before G4.
