CREATE TABLE planning_tasks (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'proposed', 'ready', 'running', 'waiting_approval', 'paused', 'completed',
        'partial', 'failed', 'cancelled', 'needs_reconciliation'
    )),
    plan_sha256 TEXT NOT NULL CHECK (length(plan_sha256) = 64),
    record_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    deadline_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_planning_tasks_host_status_updated
    ON planning_tasks (host_id, status, updated_at DESC, id DESC);

CREATE TABLE planning_approval_bindings (
    grant_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES planning_tasks(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    bound_at TEXT NOT NULL,
    UNIQUE (task_id, node_id)
);

CREATE TABLE planning_checkpoints (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL REFERENCES planning_tasks(id) ON DELETE CASCADE,
    host_id TEXT NOT NULL,
    node_id TEXT,
    phase TEXT NOT NULL CHECK (phase IN ('before_effect', 'after_effect', 'recovery')),
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_planning_checkpoints_task_sequence
    ON planning_checkpoints (task_id, sequence);

CREATE TABLE planning_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL REFERENCES planning_tasks(id) ON DELETE CASCADE,
    host_id TEXT NOT NULL,
    node_id TEXT,
    event_type TEXT NOT NULL,
    task_status TEXT NOT NULL,
    node_status TEXT,
    reason_code TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_planning_events_host_task_sequence
    ON planning_events (host_id, task_id, sequence);

CREATE TRIGGER planning_events_no_update
BEFORE UPDATE ON planning_events
BEGIN
    SELECT RAISE(ABORT, 'planning events are append-only');
END;

CREATE TABLE planning_tombstones (
    task_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    deleted_nodes INTEGER NOT NULL CHECK (deleted_nodes >= 0),
    deleted_events INTEGER NOT NULL CHECK (deleted_events >= 0),
    deleted_at TEXT NOT NULL
);
