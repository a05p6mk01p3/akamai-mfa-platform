# Change-set 06 — authenticated trusted ingress

CS06 closes the trust-boundary gap left after CS05. Actor/session/interaction
headers are no longer sufficient by themselves when
`MCP_TRUSTED_CONTEXT_MODE=request_headers` is used.

## Runtime contract

Production request-header mode now requires:

```text
MCP_TRUSTED_INGRESS_MODE=shared_secret
MCP_TRUSTED_INGRESS_HEADER_NAME=X-MFA-Ingress-Token
MCP_TRUSTED_INGRESS_SECRET_FILE=/run/secrets/akamai-mfa-mcp-ingress-token
```

LibreChat must inject a server-controlled `X-MFA-Ingress-Token` header in
addition to the CS05 actor/session/interaction headers. The ingress credential
is never a public MCP tool argument and is validated before actor/session are
accepted. Missing or incorrect credentials return `trusted_ingress_unavailable`
and make no API request.

The comparison uses `hmac.compare_digest`. The ingress credential is never
logged or fingerprinted.

## Startup fail-closed behavior

`MCP_TRUSTED_CONTEXT_MODE=request_headers` is rejected at process startup unless
`MCP_TRUSTED_INGRESS_MODE=shared_secret` and a secret of at least 32 characters
is configured. The secret may come from either `MCP_TRUSTED_INGRESS_SECRET_FILE`
(preferred) or `MCP_TRUSTED_INGRESS_SECRET` (development fallback), never both.

Static actor/session mode remains an explicit development compatibility path and
may run with ingress authentication disabled.

## Deployment defense in depth

For the release candidate, do not publish the MCP port on the host. LibreChat
should reach MCP only over the container network. The shared ingress secret is
the authentication control; network isolation is an additional boundary.

CS06 does not change the frozen six-tool schema, target ownership, confirmation,
replay, retry, or destructive execution semantics. Destructive execution remains
disabled by default.
