ALTER TABLE remote_sessions
ADD COLUMN session_kind TEXT NOT NULL DEFAULT 'signed_api'
    CHECK (session_kind IN ('signed_api', 'browser'));

ALTER TABLE remote_sessions
ADD COLUMN csrf_token_sha256 TEXT
    CHECK (csrf_token_sha256 IS NULL OR length(csrf_token_sha256) = 64);

CREATE INDEX idx_remote_sessions_kind_expiry
    ON remote_sessions (session_kind, expires_at);
