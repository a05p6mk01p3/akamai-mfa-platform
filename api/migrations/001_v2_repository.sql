CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    parent_operation_id TEXT NULL REFERENCES operations(operation_id),
    operation_type TEXT NOT NULL,
    domain TEXT NOT NULL,
    actor_context JSONB NOT NULL,
    session_context JSONB NOT NULL,
    prepared_interaction_ref TEXT NOT NULL,
    target_identity JSONB NOT NULL,
    destructive_target JSONB NULL,
    prepared_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    prepared_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ NULL,
    execution_started_at TIMESTAMPTZ NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    execution_attempts INTEGER NOT NULL DEFAULT 0,
    post_check_result JSONB NULL,
    outcome_code TEXT NULL,
    last_error JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_operations_status CHECK (
        status IN (
            'PREPARED',
            'CONFIRMED',
            'EXECUTING',
            'SUCCEEDED',
            'FAILED',
            'AMBIGUOUS',
            'VERIFYING',
            'REQUIRES_RECONFIRMATION',
            'EXPIRED',
            'CANCELLED'
        )
    ),
    CONSTRAINT ck_operations_parent_not_self CHECK (
        parent_operation_id IS NULL OR parent_operation_id <> operation_id
    )
);

CREATE INDEX IF NOT EXISTS idx_operations_status_expires
    ON operations(status, expires_at);

CREATE INDEX IF NOT EXISTS idx_operations_parent
    ON operations(parent_operation_id)
    WHERE parent_operation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS operation_events (
    event_id BIGSERIAL PRIMARY KEY,
    operation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_state TEXT NULL,
    to_state TEXT NULL,
    event_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_id TEXT NULL,
    actor_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    service_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    safe_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome_code TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_operation_events_operation_time
    ON operation_events(operation_id, event_at, event_id);

CREATE TABLE IF NOT EXISTS safe_references (
    reference_id TEXT PRIMARY KEY,
    reference_type TEXT NOT NULL,
    domain TEXT NOT NULL,
    actor_context JSONB NOT NULL,
    session_context JSONB NOT NULL,
    target_identity JSONB NOT NULL,
    internal_target JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_safe_reference_type CHECK (
        reference_type IN ('USER', 'DEVICE')
    )
);

CREATE INDEX IF NOT EXISTS idx_safe_references_expiry
    ON safe_references(expires_at);

