# CHANGESET-02A — Probe result decoding hotfix

Target: `akamai-mfa-mcp 0.5.0-v2-dev`

## Scope

This hotfix changes only the CS02 validation probe and adds a pure result
decoder test helper.

It does not change:

- MCP server behavior;
- tool schemas;
- attestation logic;
- API calls;
- destructive enablement;
- streamable HTTP/stateless configuration.

## Root cause

The original probe assumed `Client.call_tool()` would always populate
`structured_content`.

In the observed SDK behavior the tool result was returned through model-facing
`TextContent`, while `structured_content` was `None`.

That is valid MCP behavior: `structuredContent` is optional.

## Fix

The probe now:

1. uses `structured_content` when it contains an object;
2. otherwise scans text content blocks and JSON-decodes the first object;
3. prints `is_error`, content block types, and whether structured content was
   present;
4. retains the original assertions:
   - no header -> `interaction_context_unavailable`;
   - valid request header -> `not_available_in_cs02`;
   - final `PROBE_OK`.

No interaction value is logged.
