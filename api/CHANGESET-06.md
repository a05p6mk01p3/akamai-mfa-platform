# CHANGESET-06 — Execution State Machine with Simulation Backend

Target: `akamai-mfa-api 0.8.0-v2-dev`

## Goal

Validate the execution lifecycle before introducing any real destructive upstream
primitive.

## Adds

- `POST /v2/operations/{operation_id}/execute`
- `POST /v2/operations/{operation_id}/verify`
- atomic `CONFIRMED -> EXECUTING`
- TTL is permission to start, not an expiry during execution
- read-only preflight immediately after the atomic claim
- preflight failure consumes confirmation and causes:
  - `EXECUTING -> FAILED`
  - `TARGET_REVALIDATION_FAILED`
  - zero primitive calls
- mandatory post-check before success
- ambiguous lifecycle:
  - `EXECUTING -> AMBIGUOUS -> VERIFYING`
  - expected state -> `SUCCEEDED`
  - target remains -> `REQUIRES_RECONFIRMATION`
  - inconclusive -> remains `VERIFYING`
- observational `/verify` never calls mutate
- concurrent execution claim integration test
- transition + audit event written transactionally

## Critical safety property

This image contains **no real upstream destructive primitive**.

The EAA and Akamai MFA clients still have no reset/delete method.

Default:

```text
EXECUTION_BACKEND=disabled
```

Controlled validation only:

```text
EXECUTION_BACKEND=simulation
```

The simulation adapter performs no network call and no external mutation.

Simulation outcomes are process configuration, not request/model arguments:

```text
SIMULATION_PRIMITIVE_OUTCOME=expected|ambiguous|failed
SIMULATION_POSTCHECK_OUTCOME=expected|target_remains|inconclusive|wrong_state
```

## Readiness

Even with simulation enabled:

```json
"destructive_operations_enabled": false
```

and:

```json
"execution_framework_enabled": true,
"execution_backend": "simulation"
```

## Execute contract

Execute receives only `operation_id` in the URL and internal actor/session context.

It accepts no device reference, internal ID, target override, or `confirmed=true`.

## Deferred

- real EAA OTP reset primitive
- real Akamai MFA device DELETE
- child retry operation creation
- MCP v2 changes
- production enablement
