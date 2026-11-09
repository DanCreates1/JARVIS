-- Inert by default; trusted-local one-session approvals, no startup registration.
CREATE TABLE proactivity_worker_controls (
    host_id TEXT PRIMARY KEY,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    plan_json TEXT,
    expires_at TEXT NOT NULL,
    owner_token TEXT,
    lease_expires_at TEXT,
    ticks_reserved INTEGER NOT NULL DEFAULT 0 CHECK (ticks_reserved >= 0),
    updated_at TEXT NOT NULL,
    CHECK ((owner_token IS NULL) = (lease_expires_at IS NULL)),
    CHECK (enabled = 0 OR plan_json IS NOT NULL)
);
