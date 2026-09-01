CREATE TABLE action_lifecycle_events (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES action_requests(id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'proposed', 'approved', 'denied', 'expired', 'grant_issued',
            'grant_claimed', 'grant_revoked', 'grant_expired',
            'execution_started', 'broker_rejected', 'execution_completed',
            'execution_failed', 'execution_cancelled', 'execution_uncertain',
            'execution_rolled_back'
        )
    ),
    approval_id TEXT NOT NULL,
    grant_id TEXT,
    action_id TEXT NOT NULL,
    action_version TEXT NOT NULL,
    permission_level INTEGER NOT NULL CHECK (permission_level BETWEEN 0 AND 4),
    source TEXT NOT NULL CHECK (
        source IN ('local_cli', 'local_web', 'voice', 'system', 'test', 'chat', 'hands_free')
    ),
    risk TEXT NOT NULL CHECK (
        risk IN ('read_only', 'reversible', 'sensitive', 'destructive')
    ),
    approval_rule TEXT NOT NULL CHECK (
        approval_rule IN (
            'none', 'explicit_enablement', 'policy_or_explicit', 'exact_recent_auth',
            'step_up', 'disabled'
        )
    ),
    outcome TEXT,
    reason_code TEXT CHECK (reason_code IS NULL OR length(reason_code) <= 100),
    created_at TEXT NOT NULL,
    UNIQUE (request_id, sequence)
);

CREATE INDEX idx_action_lifecycle_events_created
    ON action_lifecycle_events (created_at DESC, id DESC);

CREATE INDEX idx_action_lifecycle_events_request_sequence
    ON action_lifecycle_events (request_id, sequence);

CREATE TRIGGER action_lifecycle_events_no_update
BEFORE UPDATE ON action_lifecycle_events
BEGIN
    SELECT RAISE(ABORT, 'action lifecycle events are append-only');
END;

CREATE TRIGGER action_lifecycle_events_no_delete
BEFORE DELETE ON action_lifecycle_events
BEGIN
    SELECT RAISE(ABORT, 'action lifecycle events are append-only');
END;
