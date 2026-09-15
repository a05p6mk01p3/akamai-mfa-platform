# CHANGESET-09 — Explicit Child Retry Operations

Target: `akamai-mfa-api 0.8.0-v2-dev`

## Purpose

Implement the G2-frozen retry rule:

```text
parent → REQUIRES_RECONFIRMATION
          ↓
explicit operator request to prepare another attempt
          ↓
POST /v2/operations/{parent}/retry/prepare
          ↓
new child → PREPARED
          ↓
new preflight shown
          ↓
later human interaction
          ↓
child CONFIRMED → EXECUTING
```

The original parent is never reactivated and its consumed authorization is
never reused.

## API

```http
POST /v2/operations/{parent_operation_id}/retry/prepare
```

Required trusted headers are the normal actor/session context plus
`X-MFA-Interaction`.

The route has no request body and accepts no user/device/internal target
override.

## Atomic child creation

The repository locks the parent row before creating a child.

Requirements:

- parent exists in the same actor/session context;
- parent status is exactly `REQUIRES_RECONFIRMATION`;
- child domain/type equals parent domain/type;
- at most one direct child can be created for a parent;
- parent remains `REQUIRES_RECONFIRMATION`;
- child receives a new operation ID and TTL;
- child starts `PREPARED`;
- child stores its own `prepared_interaction_ref`;
- child confirmation must occur in a later interaction.

A second retry in a chain must be prepared from the newest child if that child
later reaches `REQUIRES_RECONFIRMATION`.

## Akamai MFA retry revalidation

The API re-fetches current Akamai MFA state.

If the original bound target still exists and remains eligible:

- current non-target/protected factors are checked against the original baseline;
- a new internal baseline is captured;
- a child is prepared with the same logical target.

If the original target is already absent while the account and preserved factors
are consistent:

- no child destructive operation is created;
- the parent is observationally completed as `SUCCEEDED`.

If account/factor safety invariants are violated:

- no child is created;
- the parent fails closed where the state is conclusively unsafe.

A different newly enrolled authenticator is never silently substituted for the
original target.

## EAA retry revalidation

For an EAA parent in `REQUIRES_RECONFIRMATION`, the API re-resolves the same
safe identity and binds a freshly validated internal reset target.

The child inherits no old confirmation.

CS09 does not change the unresolved EAA post-check success criterion.

## Destructive behavior

Retry preparation itself performs no destructive POST/DELETE.

Real destructive behavior remains controlled exclusively by the configured
execution backend and requires the child's own later confirmation.
