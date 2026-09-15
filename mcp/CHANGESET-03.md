# CHANGESET-03 — Prepare wiring + prepared-interaction correlation

Target: `akamai-mfa-mcp 0.5.0-v2-dev`

## Scope

Enable only API v2 prepare operations from the MCP:

- `prepare_eaa_otp_reset`
- `prepare_akamai_mfa_device_reset`
- explicit child retry through either prepare tool using `parent_operation_id`

The following remain blocked in MCP CS03:

- API confirm
- API execute
- API verify
- destructive EAA primitive
- destructive Akamai MFA DELETE

`reset_eaa_otp` and `reset_akamai_mfa_device` still return
`reset_not_available_in_cs03` after validating trusted interaction context.

## Interaction headers

Prepare/retry API calls include:

```text
X-MFA-Actor
X-MFA-Session
X-MFA-Interaction
```

Read-only API calls still include only actor/session.

## MCP-side correlation

After a successful `status=prepared` API response, MCP records:

```text
operation_id
actor
session
prepared_interaction_ref
expires_at
```

This registry is process-local and bounded.

The API remains the persistent authority for operation state. If MCP restarts,
old correlations are intentionally unavailable and future reset must fail closed
rather than infer a prepared interaction.

## Retry

When `parent_operation_id` is supplied:

- no target override body is sent;
- EAA `user_ref` is rejected;
- Akamai MFA `user_ref` and `device_ref` are rejected;
- API owns target preservation/revalidation.

If API reports `already_completed`, no new correlation is recorded and no
confirmation is required.

## Output safety

Prepared operation responses are whitelisted. Only these safe target fields may
reach the model:

```text
user_ref
username
display_name
```

Internal target fields such as `device_id` and `eaa_reset_id` are never passed
through.

## Deployment note

The MCP remains dual-homed and must be created with network order:

```text
akamai-mfa-net
librechat-net
```

This preserves Podman DNS resolution for the private API network.
