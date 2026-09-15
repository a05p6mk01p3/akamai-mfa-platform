# Change-set 05 — Request-bound actor/session context

## Scope

CS05 removes the production dependency on static `MCP_API_ACTOR` /
`MCP_API_SESSION` by adding `MCP_TRUSTED_CONTEXT_MODE=request_headers`.

Expected LibreChat admin-owned headers:

```yaml
headers:
  X-MFA-Actor: '{{LIBRECHAT_USER_ID}}'
  X-MFA-Session: '{{LIBRECHAT_BODY_CONVERSATIONID}}'
  X-MFA-Interaction: '{{LIBRECHAT_BODY_MESSAGEID}}'
```

The MCP rejects missing, empty, oversized, control-character-bearing, and
unresolved-template actor/session values. Static mode remains for development
compatibility only. Public tool schemas do not gain actor/session arguments.

## Trust boundary

This changeset proves request binding, not cryptographic origin authentication.
The production deployment must keep MCP reachability restricted to trusted
LibreChat/runtime paths (or add an authenticated reverse-proxy/shared-secret
boundary before RC).
