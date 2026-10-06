-- Host-owned sticky privacy. Client metadata cannot clear this bit.
ALTER TABLE conversations ADD COLUMN email_private INTEGER NOT NULL DEFAULT 0
    CHECK (email_private IN (0, 1));
