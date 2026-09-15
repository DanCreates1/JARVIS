CREATE TABLE proactivity_adapter_controls (
    host_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    version INTEGER NOT NULL CHECK (version >= 1),
    kill_generation INTEGER NOT NULL CHECK (kill_generation >= 1),
    updated_at TEXT NOT NULL
);

CREATE TABLE proactivity_device_bindings (
    host_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    feature TEXT NOT NULL,
    allow_manage INTEGER NOT NULL CHECK (allow_manage IN (0, 1)),
    state TEXT NOT NULL CHECK (state IN ('active', 'revoked', 'expired')),
    version INTEGER NOT NULL CHECK (version >= 1),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (host_id, device_id, feature),
    FOREIGN KEY (device_id) REFERENCES remote_devices(id) ON DELETE CASCADE
);

CREATE INDEX idx_proactivity_device_bindings_active
    ON proactivity_device_bindings (host_id, device_id, state, expires_at, feature);

CREATE TABLE proactivity_ownerships (
    candidate_id TEXT PRIMARY KEY
        REFERENCES proactivity_dispatches(candidate_id) ON DELETE CASCADE,
    host_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    owner_kind TEXT NOT NULL CHECK (owner_kind IN ('local_host', 'device')),
    owner_id TEXT NOT NULL,
    owner_device_id TEXT,
    version INTEGER NOT NULL CHECK (version >= 1),
    lease_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (owner_kind = 'local_host' AND owner_id = host_id AND owner_device_id IS NULL
            AND lease_expires_at IS NULL) OR
        (owner_kind = 'device' AND owner_id = owner_device_id AND owner_device_id IS NOT NULL
            AND lease_expires_at IS NOT NULL)
    )
);

CREATE INDEX idx_proactivity_ownerships_host_owner
    ON proactivity_ownerships (host_id, owner_kind, owner_device_id, updated_at);

CREATE TABLE proactivity_ownership_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    host_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL
        REFERENCES proactivity_dispatches(candidate_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    owner_kind TEXT NOT NULL CHECK (owner_kind IN ('local_host', 'device')),
    owner_device_id TEXT,
    version INTEGER NOT NULL CHECK (version >= 1),
    created_at TEXT NOT NULL
);

CREATE INDEX idx_proactivity_ownership_events_candidate
    ON proactivity_ownership_events (host_id, candidate_id, sequence);

CREATE TRIGGER proactivity_ownership_events_no_update
BEFORE UPDATE ON proactivity_ownership_events
BEGIN
    SELECT RAISE(ABORT, 'proactivity ownership events are append-only');
END;

INSERT INTO proactivity_ownerships (
    candidate_id, host_id, rule_id, owner_kind, owner_id, owner_device_id,
    version, lease_expires_at, created_at, updated_at
)
SELECT
    d.candidate_id, d.host_id, d.rule_id, 'local_host', d.host_id, NULL,
    1, NULL, d.created_at, d.updated_at
FROM proactivity_dispatches AS d
WHERE NOT EXISTS (
    SELECT 1 FROM proactivity_ownerships AS o WHERE o.candidate_id = d.candidate_id
);

INSERT INTO proactivity_ownership_events (
    id, host_id, candidate_id, event_type, reason_code,
    owner_kind, owner_device_id, version, created_at
)
SELECT
    printf('proactivity-owner-event:migration:%d', o.rowid),
    o.host_id, o.candidate_id, 'local_owner_created', 'phase11c_migration_backfill',
    o.owner_kind, o.owner_device_id, o.version, o.created_at
FROM proactivity_ownerships AS o
WHERE NOT EXISTS (
    SELECT 1 FROM proactivity_ownership_events AS e WHERE e.candidate_id = o.candidate_id
);
