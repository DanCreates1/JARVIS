CREATE TABLE action_requests (
    id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL UNIQUE,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    tool_call_id TEXT,
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    actor_json TEXT NOT NULL,
    source TEXT NOT NULL CHECK (
        source IN ('local_cli', 'local_web', 'voice', 'system', 'test', 'chat', 'hands_free')
    ),
    action_id TEXT NOT NULL,
    action_version TEXT NOT NULL,
    permission_level INTEGER NOT NULL CHECK (permission_level BETWEEN 0 AND 4),
    approval_rule TEXT NOT NULL CHECK (
        approval_rule IN (
            'none', 'explicit_enablement', 'policy_or_explicit', 'exact_recent_auth',
            'step_up', 'disabled'
        )
    ),
    risk TEXT NOT NULL CHECK (
        risk IN ('read_only', 'reversible', 'sensitive', 'destructive')
    ),
    policy_version TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    normalized_arguments_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL CHECK (length(fingerprint) = 71),
    idempotency_key TEXT NOT NULL UNIQUE,
    human_effect TEXT NOT NULL,
    recovery_limits TEXT NOT NULL,
    precondition_json TEXT NOT NULL,
    request_json TEXT NOT NULL CHECK (length(request_json) <= 262144),
    decision_json TEXT CHECK (decision_json IS NULL OR length(decision_json) <= 65536),
    status TEXT NOT NULL CHECK (
        status IN (
            'pending', 'approved', 'denied', 'expired', 'claimed', 'completed',
            'failed', 'cancelled', 'uncertain', 'rolled_back'
        )
    ),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_action_requests_status_expiry
    ON action_requests (status, expires_at);

CREATE INDEX idx_action_requests_actor_session_created
    ON action_requests (actor_id, session_id, created_at DESC);

CREATE TABLE action_grants (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE REFERENCES action_requests(id) ON DELETE RESTRICT,
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action_version TEXT NOT NULL,
    permission_level INTEGER NOT NULL CHECK (permission_level BETWEEN 0 AND 4),
    policy_version TEXT NOT NULL,
    fingerprint TEXT NOT NULL CHECK (length(fingerprint) = 71),
    nonce TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    approval_id TEXT NOT NULL UNIQUE,
    approved_by TEXT NOT NULL,
    approved_by_json TEXT NOT NULL,
    grant_fingerprint TEXT NOT NULL CHECK (length(grant_fingerprint) = 71),
    grant_json TEXT NOT NULL CHECK (length(grant_json) <= 262144),
    status TEXT NOT NULL CHECK (
        status IN ('active', 'claimed', 'revoked', 'expired')
    ),
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    claimed_at TEXT,
    revoked_at TEXT
);

CREATE INDEX idx_action_grants_status_expiry
    ON action_grants (status, expires_at);

CREATE TABLE action_executions (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE REFERENCES action_requests(id) ON DELETE RESTRICT,
    grant_id TEXT NOT NULL UNIQUE REFERENCES action_grants(id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (
        status IN (
            'started', 'completed', 'failed', 'cancelled', 'uncertain', 'rolled_back'
        )
    ),
    result_json TEXT NOT NULL,
    postcondition_json TEXT NOT NULL,
    rollback_json TEXT NOT NULL,
    error_code TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms REAL CHECK (duration_ms IS NULL OR duration_ms >= 0),
    receipt_json TEXT NOT NULL
);

CREATE INDEX idx_action_executions_status_started
    ON action_executions (status, started_at);

CREATE TABLE action_audit_events (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES action_requests(id) ON DELETE RESTRICT,
    grant_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    event_type TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action_version TEXT NOT NULL,
    action_fingerprint TEXT NOT NULL CHECK (length(action_fingerprint) = 71),
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    outcome TEXT,
    error_code TEXT,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (request_id, sequence)
);

CREATE INDEX idx_action_audit_events_created
    ON action_audit_events (created_at DESC);

CREATE TRIGGER action_audit_events_no_update
BEFORE UPDATE ON action_audit_events
BEGIN
    SELECT RAISE(ABORT, 'action audit events are append-only');
END;

CREATE TRIGGER action_audit_events_no_delete
BEFORE DELETE ON action_audit_events
BEGIN
    SELECT RAISE(ABORT, 'action audit events are append-only');
END;

CREATE TABLE control_intent_events (
    event_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    source TEXT NOT NULL,
    intent TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (
        outcome IN ('proposed', 'denied', 'duplicate', 'stale', 'rate_limited', 'cancelled')
    ),
    request_id TEXT REFERENCES action_requests(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_control_intent_events_session_created
    ON control_intent_events (session_id, created_at DESC);
