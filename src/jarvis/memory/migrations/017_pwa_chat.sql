CREATE TABLE pwa_conversation_owners (
    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    host_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX pwa_conversation_owner_idx
    ON pwa_conversation_owners(host_id, device_id);

CREATE TABLE pwa_chat_requests (
    host_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    session_id TEXT NOT NULL,
    start_sequence INTEGER NOT NULL CHECK(start_sequence >= 0),
    end_sequence INTEGER,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'cancelled', 'failed', 'interrupted')),
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(host_id, device_id, request_id)
);

CREATE UNIQUE INDEX pwa_chat_one_active_device_idx
    ON pwa_chat_requests(host_id, device_id) WHERE status = 'running';

CREATE INDEX pwa_chat_conversation_idx
    ON pwa_chat_requests(conversation_id, created_at DESC);

-- Preserve a content-free no-replay receipt when local conversation deletion clears history.
CREATE TRIGGER pwa_chat_conversation_deleted BEFORE DELETE ON conversations
BEGIN
    UPDATE pwa_chat_requests
    SET status='interrupted',
        result_json=json_object(
            'request_id',request_id,'conversation_id',NULL,'status','interrupted','reply',NULL,
            'error',json_object('code','conversation_deleted','message','Conversation was deleted.')
        )
    WHERE conversation_id=OLD.id;
END;
