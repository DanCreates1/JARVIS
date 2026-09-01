CREATE TABLE memory_items (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    category TEXT NOT NULL CHECK (
        category IN ('working', 'episodic', 'profile', 'semantic', 'task')
    ),
    state TEXT NOT NULL CHECK (
        state IN ('candidate', 'committed', 'corrected', 'expired', 'rejected')
    ),
    key TEXT CHECK (key IS NULL OR (length(key) BETWEEN 1 AND 500)),
    content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 100000),
    content_sha256 TEXT CHECK (content_sha256 IS NULL OR length(content_sha256) = 64),
    structured_json TEXT NOT NULL CHECK (length(structured_json) <= 65536),
    sensitivity TEXT NOT NULL CHECK (sensitivity IN ('public', 'private', 'unknown')),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    retention_class TEXT NOT NULL CHECK (
        retention_class IN ('volatile', 'short', 'standard', 'long', 'indefinite')
    ),
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accessed_at TEXT,
    version INTEGER NOT NULL CHECK (version >= 1),
    supersedes_id TEXT REFERENCES memory_items(id) ON DELETE SET NULL,
    conflict_group_id TEXT,
    is_derived INTEGER NOT NULL DEFAULT 0 CHECK (is_derived IN (0, 1)),
    CHECK (category != 'working' OR expires_at IS NOT NULL)
);

CREATE INDEX idx_memory_items_host_state_category
    ON memory_items (host_id, state, category, updated_at DESC);

CREATE INDEX idx_memory_items_host_key
    ON memory_items (host_id, category, key, state);

CREATE INDEX idx_memory_items_expiry
    ON memory_items (host_id, expires_at)
    WHERE expires_at IS NOT NULL;

CREATE INDEX idx_memory_items_content_hash
    ON memory_items (host_id, category, content_sha256, state);

CREATE TABLE memory_provenance (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('conversation', 'message', 'tool', 'import', 'explicit', 'derived')
    ),
    source_id TEXT NOT NULL CHECK (length(source_id) BETWEEN 1 AND 500),
    source_label TEXT CHECK (source_label IS NULL OR length(source_label) <= 2000),
    conversation_id TEXT CHECK (conversation_id IS NULL OR length(conversation_id) <= 200),
    message_id TEXT CHECK (message_id IS NULL OR length(message_id) <= 200),
    tool_call_id TEXT CHECK (tool_call_id IS NULL OR length(tool_call_id) <= 200),
    import_uri TEXT CHECK (import_uri IS NULL OR length(import_uri) <= 2000),
    source_content_sha256 TEXT CHECK (
        source_content_sha256 IS NULL OR length(source_content_sha256) = 64
    ),
    trust TEXT NOT NULL CHECK (trust IN ('trusted_host', 'local_system', 'untrusted_content')),
    created_at TEXT NOT NULL,
    UNIQUE (memory_id, source_type, source_id)
);

CREATE INDEX idx_memory_provenance_source
    ON memory_provenance (source_type, source_id, memory_id);

CREATE INDEX idx_memory_provenance_conversation
    ON memory_provenance (conversation_id, message_id, memory_id);

CREATE TABLE memory_derivations (
    source_memory_id TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    derived_memory_id TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    derivation_type TEXT NOT NULL CHECK (
        derivation_type IN ('summary', 'normalization', 'task_rollup', 'profile_rollup')
    ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (source_memory_id, derived_memory_id),
    CHECK (source_memory_id != derived_memory_id)
);

CREATE INDEX idx_memory_derivations_derived
    ON memory_derivations (derived_memory_id, source_memory_id);

CREATE TABLE memory_conflicts (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    left_memory_id TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    right_memory_id TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('open', 'resolved', 'dismissed')),
    winner_memory_id TEXT REFERENCES memory_items(id) ON DELETE SET NULL,
    reason_code TEXT NOT NULL CHECK (length(reason_code) BETWEEN 1 AND 100),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    CHECK (left_memory_id != right_memory_id),
    UNIQUE (left_memory_id, right_memory_id)
);

CREATE INDEX idx_memory_conflicts_host_status
    ON memory_conflicts (host_id, status, created_at DESC);

CREATE TABLE memory_retention_rules (
    host_id TEXT NOT NULL,
    category TEXT NOT NULL CHECK (
        category IN ('working', 'episodic', 'profile', 'semantic', 'task')
    ),
    retention_days INTEGER CHECK (retention_days IS NULL OR retention_days BETWEEN 1 AND 36500),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (host_id, category)
);

CREATE TABLE memory_tombstones (
    memory_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    category TEXT NOT NULL CHECK (
        category IN ('working', 'episodic', 'profile', 'semantic', 'task')
    ),
    last_version INTEGER NOT NULL CHECK (last_version >= 1),
    reason_code TEXT NOT NULL CHECK (length(reason_code) BETWEEN 1 AND 100),
    deleted_at TEXT NOT NULL
);

CREATE INDEX idx_memory_tombstones_host_deleted
    ON memory_tombstones (host_id, deleted_at DESC);

CREATE TABLE memory_events (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'candidate_created', 'explicitly_committed', 'promoted', 'rejected',
            'corrected', 'expired', 'conflict_opened', 'conflict_resolved',
            'deduplicated', 'exported', 'deleted'
        )
    ),
    category TEXT NOT NULL CHECK (
        category IN ('working', 'episodic', 'profile', 'semantic', 'task')
    ),
    state TEXT NOT NULL CHECK (
        state IN ('candidate', 'committed', 'corrected', 'expired', 'rejected', 'deleted')
    ),
    reason_code TEXT CHECK (reason_code IS NULL OR length(reason_code) <= 100),
    created_at TEXT NOT NULL
);

CREATE INDEX idx_memory_events_host_created
    ON memory_events (host_id, created_at DESC, id DESC);

CREATE TRIGGER memory_events_no_update
BEFORE UPDATE ON memory_events
BEGIN
    SELECT RAISE(ABORT, 'memory events are append-only');
END;

CREATE TRIGGER memory_events_no_delete
BEFORE DELETE ON memory_events
BEGIN
    SELECT RAISE(ABORT, 'memory events are append-only');
END;

CREATE VIRTUAL TABLE memory_fts USING fts5(
    memory_id UNINDEXED,
    host_id UNINDEXED,
    category UNINDEXED,
    key,
    content,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER memory_items_fts_insert
AFTER INSERT ON memory_items
WHEN NEW.state = 'committed'
BEGIN
    INSERT INTO memory_fts (memory_id, host_id, category, key, content)
    VALUES (NEW.id, NEW.host_id, NEW.category, COALESCE(NEW.key, ''), NEW.content);
END;

CREATE TRIGGER memory_items_fts_update
AFTER UPDATE OF state, key, content, host_id, category ON memory_items
BEGIN
    DELETE FROM memory_fts WHERE memory_id = OLD.id;
    INSERT INTO memory_fts (memory_id, host_id, category, key, content)
    SELECT NEW.id, NEW.host_id, NEW.category, COALESCE(NEW.key, ''), NEW.content
    WHERE NEW.state = 'committed';
END;

CREATE TRIGGER memory_items_fts_delete
AFTER DELETE ON memory_items
BEGIN
    DELETE FROM memory_fts WHERE memory_id = OLD.id;
END;

INSERT INTO memory_items (
    id, host_id, category, state, key, content, content_sha256, structured_json,
    sensitivity, confidence, retention_class, expires_at, created_at, updated_at,
    accessed_at, version, supersedes_id, conflict_group_id, is_derived
)
SELECT
    id,
    'host-legacy',
    CASE kind WHEN 'profile' THEN 'profile' WHEN 'task' THEN 'task' ELSE 'semantic' END,
    'committed',
    NULL,
    content,
    NULL,
    metadata_json,
    sensitivity,
    1.0,
    'indefinite',
    NULL,
    created_at,
    created_at,
    NULL,
    1,
    NULL,
    NULL,
    0
FROM memory_records;

INSERT INTO memory_provenance (
    id, memory_id, source_type, source_id, source_label, conversation_id, message_id,
    tool_call_id, import_uri, source_content_sha256, trust, created_at
)
SELECT
    'legacy-provenance-' || id,
    id,
    'explicit',
    'legacy-memory-record-' || id,
    provenance,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'trusted_host',
    created_at
FROM memory_records;
