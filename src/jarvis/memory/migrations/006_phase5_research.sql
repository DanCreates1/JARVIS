CREATE TABLE research_sources (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    url TEXT NOT NULL CHECK (length(url) BETWEEN 1 AND 2048),
    publisher TEXT CHECK (publisher IS NULL OR length(publisher) BETWEEN 1 AND 500),
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 1000),
    topic TEXT NOT NULL CHECK (length(topic) BETWEEN 1 AND 500),
    media_type TEXT NOT NULL CHECK (length(media_type) BETWEEN 1 AND 200),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    extracted_text TEXT NOT NULL CHECK (length(extracted_text) BETWEEN 1 AND 500000),
    retrieved_at TEXT NOT NULL,
    published_at TEXT,
    last_checked_at TEXT NOT NULL,
    usage_notes TEXT NOT NULL CHECK (length(usage_notes) <= 2000),
    state TEXT NOT NULL CHECK (state IN ('active', 'stale', 'unavailable')),
    version INTEGER NOT NULL CHECK (version >= 1),
    supersedes_id TEXT REFERENCES research_sources(id) ON DELETE SET NULL,
    etag TEXT CHECK (etag IS NULL OR length(etag) <= 500),
    last_modified TEXT CHECK (last_modified IS NULL OR length(last_modified) <= 500),
    UNIQUE (host_id, url, version)
);

CREATE INDEX idx_research_sources_host_state_topic
    ON research_sources (host_id, state, topic, retrieved_at DESC);

CREATE INDEX idx_research_sources_host_url
    ON research_sources (host_id, url, version DESC);

CREATE VIRTUAL TABLE research_source_fts USING fts5(
    source_id UNINDEXED,
    host_id UNINDEXED,
    title,
    topic,
    extracted_text,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER research_sources_fts_insert
AFTER INSERT ON research_sources
WHEN NEW.state = 'active'
BEGIN
    INSERT INTO research_source_fts (source_id, host_id, title, topic, extracted_text)
    VALUES (NEW.id, NEW.host_id, NEW.title, NEW.topic, NEW.extracted_text);
END;

CREATE TRIGGER research_sources_fts_update
AFTER UPDATE OF state, title, topic, extracted_text, host_id ON research_sources
BEGIN
    DELETE FROM research_source_fts WHERE source_id = OLD.id;
    INSERT INTO research_source_fts (source_id, host_id, title, topic, extracted_text)
    SELECT NEW.id, NEW.host_id, NEW.title, NEW.topic, NEW.extracted_text
    WHERE NEW.state = 'active';
END;

CREATE TRIGGER research_sources_fts_delete
AFTER DELETE ON research_sources
BEGIN
    DELETE FROM research_source_fts WHERE source_id = OLD.id;
END;

CREATE TABLE research_claims (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    topic TEXT NOT NULL CHECK (length(topic) BETWEEN 1 AND 500),
    statement TEXT NOT NULL CHECK (length(statement) BETWEEN 1 AND 10000),
    status TEXT NOT NULL CHECK (
        status IN ('verified', 'likely', 'hypothesis', 'opinion', 'stale', 'conflicting')
    ),
    lifecycle TEXT NOT NULL CHECK (lifecycle IN ('active', 'superseded')),
    is_material INTEGER NOT NULL CHECK (is_material IN (0, 1)),
    is_inference INTEGER NOT NULL CHECK (is_inference IN (0, 1)),
    uncertainty TEXT NOT NULL CHECK (length(uncertainty) <= 2000),
    version INTEGER NOT NULL CHECK (version >= 1),
    supersedes_id TEXT REFERENCES research_claims(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_research_claims_host_lifecycle_topic
    ON research_claims (host_id, lifecycle, topic, updated_at DESC);

CREATE TABLE research_claim_citations (
    claim_id TEXT NOT NULL REFERENCES research_claims(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES research_sources(id) ON DELETE CASCADE,
    locator TEXT NOT NULL CHECK (length(locator) BETWEEN 1 AND 500),
    quote TEXT CHECK (quote IS NULL OR length(quote) <= 1000),
    PRIMARY KEY (claim_id, source_id)
);

CREATE INDEX idx_research_claim_citations_source
    ON research_claim_citations (source_id, claim_id);

CREATE TABLE research_conflicts (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    left_claim_id TEXT NOT NULL REFERENCES research_claims(id) ON DELETE CASCADE,
    right_claim_id TEXT NOT NULL REFERENCES research_claims(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('open', 'resolved', 'dismissed')),
    winner_claim_id TEXT REFERENCES research_claims(id) ON DELETE SET NULL,
    reason_code TEXT NOT NULL CHECK (length(reason_code) BETWEEN 1 AND 100),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    CHECK (left_claim_id != right_claim_id)
);

CREATE INDEX idx_research_conflicts_host_status
    ON research_conflicts (host_id, status, created_at DESC);

CREATE UNIQUE INDEX idx_research_conflicts_open_pair
    ON research_conflicts (left_claim_id, right_claim_id)
    WHERE status = 'open';

CREATE TABLE research_source_tombstones (
    source_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    last_version INTEGER NOT NULL CHECK (last_version >= 1),
    reason_code TEXT NOT NULL CHECK (length(reason_code) BETWEEN 1 AND 100),
    deleted_at TEXT NOT NULL
);

CREATE TABLE research_claim_tombstones (
    claim_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    last_version INTEGER NOT NULL CHECK (last_version >= 1),
    reason_code TEXT NOT NULL CHECK (length(reason_code) BETWEEN 1 AND 100),
    deleted_at TEXT NOT NULL
);

CREATE TABLE research_events (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('source', 'claim', 'conflict', 'export')),
    resource_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'source_recorded', 'source_revalidated', 'source_updated', 'source_unavailable',
            'source_deleted', 'claim_recorded', 'claim_updated', 'claim_staled', 'claim_deleted',
            'conflict_opened', 'conflict_resolved', 'conflict_dismissed', 'exported'
        )
    ),
    reason_code TEXT CHECK (reason_code IS NULL OR length(reason_code) <= 100),
    created_at TEXT NOT NULL
);

CREATE INDEX idx_research_events_host_created
    ON research_events (host_id, created_at DESC, id DESC);

CREATE TRIGGER research_events_no_update
BEFORE UPDATE ON research_events
BEGIN
    SELECT RAISE(ABORT, 'research events are append-only');
END;

CREATE TRIGGER research_events_no_delete
BEFORE DELETE ON research_events
BEGIN
    SELECT RAISE(ABORT, 'research events are append-only');
END;
