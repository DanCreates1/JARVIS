-- Control requests are independent of optimistic execution checkpoints.
CREATE TABLE planning_controls (
    task_id TEXT PRIMARY KEY REFERENCES planning_tasks(id) ON DELETE CASCADE,
    pause_requested INTEGER NOT NULL DEFAULT 0 CHECK (pause_requested IN (0, 1)),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1))
);
