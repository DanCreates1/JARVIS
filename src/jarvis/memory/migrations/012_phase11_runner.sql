CREATE TABLE proactivity_dispatches (
    candidate_id TEXT PRIMARY KEY
        REFERENCES proactivity_candidates(id) ON DELETE CASCADE,
    host_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'claimed', 'notified', 'snoozed', 'handed_off', 'dismissed',
        'cancelled', 'expired', 'failed'
    )),
    version INTEGER NOT NULL CHECK (version >= 1),
    attempts INTEGER NOT NULL CHECK (attempts BETWEEN 1 AND 10),
    lease_id TEXT UNIQUE,
    lease_expires_at TEXT,
    notification_id TEXT UNIQUE,
    snoozed_until TEXT,
    task_id TEXT UNIQUE,
    task_version INTEGER,
    task_plan_sha256 TEXT,
    failure_code TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK ((lease_id IS NULL) = (lease_expires_at IS NULL)),
    CHECK ((task_id IS NULL) = (task_version IS NULL)),
    CHECK ((task_id IS NULL) = (task_plan_sha256 IS NULL)),
    CHECK (task_plan_sha256 IS NULL OR length(task_plan_sha256) = 64)
);

CREATE INDEX idx_proactivity_dispatches_host_state
    ON proactivity_dispatches (host_id, state, updated_at, candidate_id);

CREATE TABLE proactivity_notifications (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL UNIQUE
        REFERENCES proactivity_dispatches(candidate_id) ON DELETE CASCADE,
    feature TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'active', 'snoozed', 'handed_off', 'dismissed', 'cancelled', 'expired'
    )),
    available_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_proactivity_notifications_host_state
    ON proactivity_notifications (host_id, state, available_at, id);

CREATE TABLE proactivity_runner_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    host_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL
        REFERENCES proactivity_candidates(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_proactivity_runner_events_host_candidate
    ON proactivity_runner_events (host_id, candidate_id, sequence);

CREATE TRIGGER proactivity_runner_events_no_update
BEFORE UPDATE ON proactivity_runner_events
BEGIN
    SELECT RAISE(ABORT, 'proactivity runner events are append-only');
END;
