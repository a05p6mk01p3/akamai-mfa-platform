# CHANGESET-02 — PostgreSQL Repository Foundation

Target: `akamai-mfa-api 0.8.0-v2-dev`

## Scope

This change-set extends the validated read-only change-set 01 with:

- PostgreSQL adapter using Psycopg 3;
- first SQL migration;
- `operations` authoritative state table;
- append-oriented `operation_events`;
- `safe_references`;
- PostgreSQL `OperationRepository`;
- atomic `CONFIRMED -> EXECUTING` claim;
- context-bound safe references;
- deny-by-default device-ref issuing policy;
- DB migration/check scripts;
- integration tests that run only when `TEST_DATABASE_URL` is configured.

## Safety boundary

Still absent:

- EAA OTP reset primitive;
- Akamai device DELETE primitive;
- destructive API routes;
- `OperationManager` destructive execution;
- MCP changes.

`/ready` must continue to report:

```json
"destructive_operations_enabled": false
```

## PostgreSQL validation target

The database must only be attached to `akamai-mfa-net`.

Recommended temporary test container name:

```text
akamai-mfa-postgres-v2-test
```

Do not connect it to `librechat-net`.

## Important

The `prepared_interaction_ref`/`confirmation_interaction_ref` fields are internal attestation inputs.
No public LLM tool receives them.

The MCP later-interaction attestation mechanism remains a separate implementation task.
