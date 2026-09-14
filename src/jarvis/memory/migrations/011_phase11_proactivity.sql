CREATE TABLE proactivity_rules (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    status TEXT NOT NULL,
    proposal_sha256 TEXT NOT NULL,
    record_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (host_id, id)
);

CREATE INDEX idx_proactivity_rules_host_status
ON proactivity_rules (host_id, status, updated_at DESC);

CREATE TABLE proactivity_activations (
    approval_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    proposal_sha256 TEXT NOT NULL,
    interface TEXT NOT NULL CHECK (interface = 'trusted_local_cli'),
    approved_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT NOT NULL,
    FOREIGN KEY (rule_id) REFERENCES proactivity_rules(id) ON DELETE CASCADE
);

CREATE TABLE proactivity_candidates (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    feature TEXT NOT NULL,
    occurrence_key TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    attention_seconds INTEGER NOT NULL CHECK (attention_seconds BETWEEN 1 AND 60),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE (host_id, rule_id, occurrence_key),
    FOREIGN KEY (rule_id) REFERENCES proactivity_rules(id) ON DELETE CASCADE
);

CREATE INDEX idx_proactivity_candidates_host_created
ON proactivity_candidates (host_id, created_at DESC);

CREATE INDEX idx_proactivity_candidates_host_expiry
ON proactivity_candidates (host_id, expires_at);

CREATE TABLE proactivity_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    host_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    candidate_id TEXT,
    event_type TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (rule_id) REFERENCES proactivity_rules(id) ON DELETE CASCADE,
    FOREIGN KEY (candidate_id) REFERENCES proactivity_candidates(id) ON DELETE CASCADE
);

CREATE INDEX idx_proactivity_events_host_rule
ON proactivity_events (host_id, rule_id, sequence);

CREATE TABLE proactivity_tombstones (
    rule_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    deleted_candidates INTEGER NOT NULL CHECK (deleted_candidates >= 0),
    deleted_events INTEGER NOT NULL CHECK (deleted_events >= 0),
    deleted_at TEXT NOT NULL
);
