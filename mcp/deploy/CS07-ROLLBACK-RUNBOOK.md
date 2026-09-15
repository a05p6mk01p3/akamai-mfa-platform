# CS07 rollback runbook

CS07 rollback is an MCP deployment rollback, not yet the full G4 platform
rollback rehearsal.

## Preconditions

- Frozen v1 image/deployment is preserved and never modified in place.
- Pre-CS07 LibreChat YAML and source Quadlet snapshots exist on the VM.
- Secret values are not copied into rollback instructions or logs.

## Candidate rollback sequence

1. Restore the pre-CS07 LibreChat YAML/server selection snapshot.
2. Restart LibreChat and verify the previously accepted MCP endpoint is reachable.
3. Stop/disable `akamai-mfa-mcp-v2.service`.
4. Restore the previous MCP v2 source Quadlet only if the candidate overwrote it.
5. `systemctl daemon-reload` and verify frozen v1 remains unchanged/running.
6. Run read-only health/search validation. Do not use destructive actions as a
   rollback probe.

## Rehearsal evidence to record

- start/end timestamps;
- exact image ID/digest before and after;
- LibreChat endpoint selected before and after;
- no secret value in command output;
- no destructive API/upstream request;
- total recovery time.

The later G4 rehearsal must cover the full API + MCP + config rollback to frozen
v1. CS07 only proves that the MCP candidate cutover is operationally reversible.
