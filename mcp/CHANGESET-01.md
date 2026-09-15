# CHANGESET-01 — MCP v2 read-only bridge

Target: `akamai-mfa-mcp 0.5.0-v2-dev`

## Frozen baseline retained

- Python MCP SDK 2.2.0
- `transport="streamable-http"`
- `stateless_http=True`
- `json_response=True`
- `/mcp`
- non-root container
- MCP remains the dual-homed bridge; networking is deployment-owned

The temporary stateful troubleshooting variant is not used.

## Public tool catalog

Exactly six G2-frozen tool names are registered:

1. `search_eaa_user` — implemented read-only
2. `prepare_eaa_otp_reset` — CS01 fail-closed stub
3. `reset_eaa_otp` — CS01 fail-closed stub
4. `get_akamai_mfa_status` — implemented read-only
5. `prepare_akamai_mfa_device_reset` — CS01 fail-closed stub
6. `reset_akamai_mfa_device` — CS01 fail-closed stub

The reset tools expose no `confirmed` argument.

## API v2 mappings enabled

```http
GET /v2/eaa/users/search?q={query}
GET /v2/akamai-mfa/users/{user_ref}/status
```

Every enabled API request carries deployment/runtime-owned:

```text
X-MFA-Actor
X-MFA-Session
```

No internal ID, contract ID, directory ID or raw upstream identifier is accepted
by any MCP tool.

## Result safety

The MCP whitelists output fields rather than blindly relaying the API response.
It preserves:

- EAA `found` / `ambiguous` / `not_found`;
- Akamai MFA `account_present`, `account_status`, `business_state`;
- actual safe factors and backend-owned `classification` / `reset_eligible`;
- `device_ref` only for eligible factors.

If an API regression ever places a `device_ref` on a protected/non-eligible
factor, CS01 clears it before returning MCP output.

## Not implemented in CS01

- prepare API calls
- operation correlation storage
- trusted `current_interaction_ref`
- same-interaction prepare→reset enforcement
- confirmation attestation
- API confirm→execute mapping
- observational verify
- child retry orchestration

Those are intentionally blocked rather than approximated.
