CREATE TABLE research_reports (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    objective TEXT NOT NULL CHECK (length(objective) BETWEEN 1 AND 2000),
    answer TEXT NOT NULL CHECK (length(answer) BETWEEN 1 AND 100000),
    report_sha256 TEXT NOT NULL CHECK (length(report_sha256) = 64),
    state TEXT NOT NULL CHECK (state IN ('current', 'superseded')),
    supersedes_id TEXT REFERENCES research_reports(id) ON DELETE SET NULL,
    approved_interface TEXT NOT NULL CHECK (
        approved_interface IN ('local_cli', 'local_web', 'trusted_api', 'test')
    ),
    approved_at TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    UNIQUE (host_id, report_sha256)
);

CREATE INDEX idx_research_reports_host_state_generated
    ON research_reports (host_id, state, generated_at DESC);

CREATE TABLE research_report_sources (
    report_id TEXT NOT NULL REFERENCES research_reports(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES research_sources(id) ON DELETE CASCADE,
    PRIMARY KEY (report_id, source_id)
);

CREATE TABLE research_report_claims (
    report_id TEXT NOT NULL REFERENCES research_reports(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES research_claims(id) ON DELETE CASCADE,
    PRIMARY KEY (report_id, claim_id)
);

CREATE TABLE research_unanswered_questions (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    report_id TEXT NOT NULL REFERENCES research_reports(id) ON DELETE CASCADE,
    question TEXT NOT NULL CHECK (length(question) BETWEEN 1 AND 2000),
    status TEXT NOT NULL CHECK (status IN ('open', 'answered', 'dismissed')),
    answer_claim_id TEXT REFERENCES research_claims(id) ON DELETE SET NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (report_id, question)
);

CREATE INDEX idx_research_unanswered_host_status_updated
    ON research_unanswered_questions (host_id, status, updated_at DESC);

CREATE TABLE research_workflow_events (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('report', 'question')),
    resource_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('report_approved', 'report_superseded', 'question_opened',
                       'question_answered', 'question_dismissed')
    ),
    interface TEXT CHECK (
        interface IS NULL OR interface IN ('local_cli', 'local_web', 'trusted_api', 'test')
    ),
    created_at TEXT NOT NULL
);

CREATE INDEX idx_research_workflow_events_host_created
    ON research_workflow_events (host_id, created_at DESC, id DESC);

CREATE TRIGGER research_workflow_events_no_update
BEFORE UPDATE ON research_workflow_events
BEGIN
    SELECT RAISE(ABORT, 'research workflow events are append-only');
END;

CREATE TRIGGER research_workflow_events_no_delete
BEFORE DELETE ON research_workflow_events
BEGIN
    SELECT RAISE(ABORT, 'research workflow events are append-only');
END;
