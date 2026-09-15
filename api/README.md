# Akamai MFA API 0.8.0-v2-dev — Change-set 01 (read-only foundation)

This package is the first implementation change-set after G1/G2 freeze.

Included:

- separated EAA and Akamai MFA upstream clients;
- read-only Akamai MFA factor/device discovery (`includeDevices=true`);
- explicit EAA/Akamai MFA domain models;
- deny-by-default `DeviceClassificationPolicy`;
- EAA exact/ambiguous/not-found resolution logic;
- Akamai MFA status/business-state logic;
- existing structured audit formatter and request-id middleware;
- health/readiness endpoints.

Intentionally **not included**:

- EAA OTP reset;
- Akamai MFA DELETE;
- public v2 search/status endpoints (safe references require their repository/context implementation);
- Operation Repository / PostgreSQL;
- Operation Manager;
- prepare / confirm / execute / verify;
- child-operation retry lifecycle.

This package cannot perform a destructive Akamai/EAA action by design.


## Change-set 02

PostgreSQL repository and safe-reference foundation added. Destructive operations remain disabled.


## Change-set 03

Read-only v2 endpoints now use PostgreSQL-backed opaque user/device references. Destructive operations remain disabled.


## Change-set 04

Prepare-only operations are now exposed. They revalidate and bind internal targets in PostgreSQL, but no upstream mutation primitive exists and confirm/execute remain absent.


## Change-set 05

Contextual later-interaction confirmation is exposed. Execute and all upstream destructive primitives remain unavailable.


## Change-set 06

Execution lifecycle is testable through a pure simulation backend. Real upstream mutations remain absent and disabled.


## Change-set 07

Adds an explicitly gated EAA OTP tenant-validation backend. It can issue one real reset POST but deliberately leaves post-check in VERIFYING until the tenant-specific success state is proven.


## Change-set 07A

Hotfix: real EAA tenant-validation executions now report `simulation=false`; safe primitive metadata is preserved across verification observations.


## Change-set 08

Adds an explicitly gated single-device Akamai MFA DELETE backend with objective post-check: target absent, account remains, and all non-target/protected factors remain.


## Change-set 09

Adds G2-frozen explicit child retry preparation after `REQUIRES_RECONFIRMATION`. Parents are never reactivated; children receive independent TTL, target revalidation and later-human confirmation.
