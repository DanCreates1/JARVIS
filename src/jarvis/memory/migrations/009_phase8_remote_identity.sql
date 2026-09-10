CREATE TABLE remote_enrollments (
    id TEXT PRIMARY KEY,
    challenge_sha256 TEXT NOT NULL CHECK (length(challenge_sha256) = 64),
    host_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    device_type TEXT NOT NULL CHECK (device_type IN ('phone', 'browser', 'laptop', 'wearable', 'service')),
    scopes_json TEXT NOT NULL,
    risk_ceiling INTEGER NOT NULL CHECK (risk_ceiling BETWEEN 0 AND 2),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE INDEX idx_remote_enrollments_expiry ON remote_enrollments (expires_at);

CREATE TABLE remote_devices (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    device_type TEXT NOT NULL CHECK (device_type IN ('phone', 'browser', 'laptop', 'wearable', 'service')),
    public_key TEXT NOT NULL,
    key_fingerprint TEXT NOT NULL UNIQUE CHECK (length(key_fingerprint) = 64),
    key_version INTEGER NOT NULL CHECK (key_version >= 1),
    scopes_json TEXT NOT NULL,
    risk_ceiling INTEGER NOT NULL CHECK (risk_ceiling BETWEEN 0 AND 2),
    protocol_version TEXT NOT NULL CHECK (protocol_version = '1'),
    state TEXT NOT NULL CHECK (state IN ('active', 'expired', 'revoked')),
    enrolled_at TEXT NOT NULL,
    credential_expires_at TEXT NOT NULL,
    last_seen_at TEXT,
    revoked_at TEXT
);

CREATE INDEX idx_remote_devices_host_state ON remote_devices (host_id, state, enrolled_at DESC);

CREATE TABLE remote_sessions (
    id TEXT PRIMARY KEY,
    token_sha256 TEXT NOT NULL UNIQUE CHECK (length(token_sha256) = 64),
    device_id TEXT NOT NULL REFERENCES remote_devices(id) ON DELETE CASCADE,
    key_version INTEGER NOT NULL CHECK (key_version >= 1),
    audience TEXT NOT NULL CHECK (audience = 'jarvis-api'),
    scopes_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT,
    revoked_at TEXT,
    revoke_reason TEXT
);

CREATE INDEX idx_remote_sessions_device_expiry ON remote_sessions (device_id, expires_at);

CREATE TABLE remote_nonces (
    device_id TEXT NOT NULL REFERENCES remote_devices(id) ON DELETE CASCADE,
    nonce TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (device_id, nonce)
);

CREATE INDEX idx_remote_nonces_expiry ON remote_nonces (expires_at);

CREATE TABLE remote_audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('allowed', 'denied', 'succeeded')),
    reason_code TEXT NOT NULL,
    device_id TEXT,
    session_id TEXT,
    enrollment_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_remote_audit_device_sequence
    ON remote_audit_events (device_id, sequence DESC);

CREATE TRIGGER remote_audit_events_no_update
BEFORE UPDATE ON remote_audit_events
BEGIN
    SELECT RAISE(ABORT, 'remote audit events are append-only');
END;
