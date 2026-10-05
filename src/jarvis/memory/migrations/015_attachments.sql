ALTER TABLE conversations ADD COLUMN attachment_private INTEGER NOT NULL DEFAULT 0
    CHECK(attachment_private IN (0, 1));
CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('processing', 'ready', 'failed')),
    byte_size INTEGER NOT NULL CHECK(byte_size > 0),
    storage_bytes INTEGER NOT NULL CHECK(storage_bytes > 0),
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    error_code TEXT,
    body BLOB NOT NULL,
    image BLOB,
    derived_sha256 TEXT,
    UNIQUE(host_id, conversation_id, sha256, media_type)
);
CREATE INDEX attachments_scope ON attachments(host_id, conversation_id, expires_at);
CREATE TABLE attachment_chunks (
    attachment_id TEXT NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY(attachment_id, ordinal)
);
