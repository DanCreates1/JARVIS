CREATE TABLE memory_records (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('note', 'profile', 'task')),
    content TEXT NOT NULL,
    provenance TEXT NOT NULL,
    sensitivity TEXT NOT NULL CHECK (sensitivity IN ('public', 'private', 'unknown')),
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_memory_records_kind_created
    ON memory_records (kind, created_at DESC);

CREATE TABLE audit_records (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (
        outcome IN ('requested', 'allowed', 'denied', 'completed', 'failed')
    ),
    risk TEXT NOT NULL CHECK (
        risk IN ('read_only', 'reversible', 'sensitive', 'destructive')
    ),
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_audit_records_conversation_created
    ON audit_records (conversation_id, created_at DESC);

CREATE TABLE approval_records (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'approved', 'denied', 'expired', 'consumed')
    ),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

