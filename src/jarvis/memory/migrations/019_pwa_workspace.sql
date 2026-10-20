-- Metadata inherits exact phone ownership; no local history is backfilled.
ALTER TABLE pwa_conversation_owners ADD COLUMN title TEXT;
ALTER TABLE pwa_conversation_owners ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pwa_conversation_owners ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pwa_conversation_owners ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;

CREATE TABLE pwa_library_versions (
    host_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(host_id, device_id)
);
INSERT INTO pwa_library_versions(host_id,device_id)
    SELECT DISTINCT host_id,device_id FROM pwa_conversation_owners;
CREATE TRIGGER pwa_library_created AFTER INSERT ON pwa_conversation_owners BEGIN
    INSERT INTO pwa_library_versions VALUES(NEW.host_id,NEW.device_id,1)
    ON CONFLICT(host_id,device_id) DO UPDATE SET revision=revision+1;
END;
CREATE TRIGGER pwa_library_metadata AFTER UPDATE ON pwa_conversation_owners BEGIN
    UPDATE pwa_library_versions SET revision=revision+1
    WHERE host_id=NEW.host_id AND device_id=NEW.device_id;
END;
CREATE TRIGGER pwa_library_updated AFTER UPDATE ON conversations BEGIN
    UPDATE pwa_library_versions SET revision=revision+1 WHERE (host_id,device_id) IN
    (SELECT host_id,device_id FROM pwa_conversation_owners WHERE conversation_id=NEW.id);
END;
CREATE TRIGGER pwa_library_deleted BEFORE DELETE ON pwa_conversation_owners BEGIN
    UPDATE pwa_library_versions SET revision=revision+1
    WHERE host_id=OLD.host_id AND device_id=OLD.device_id;
END;

-- Content-free request provenance survives ordinary attachment retention cleanup.
CREATE TABLE pwa_attachment_requests (
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL,
    attachment_id TEXT NOT NULL,
    PRIMARY KEY(conversation_id,request_id,attachment_id)
);
CREATE INDEX pwa_attachment_conversation ON pwa_attachment_requests(conversation_id,attachment_id);

CREATE TABLE pwa_task_versions(host_id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0);
INSERT INTO pwa_task_versions(host_id) SELECT DISTINCT host_id FROM planning_tasks;
CREATE TRIGGER pwa_task_created AFTER INSERT ON planning_tasks BEGIN
    INSERT INTO pwa_task_versions VALUES(NEW.host_id,1)
    ON CONFLICT(host_id) DO UPDATE SET revision=revision+1;
END;
CREATE TRIGGER pwa_task_updated AFTER UPDATE ON planning_tasks BEGIN
    UPDATE pwa_task_versions SET revision=revision+1 WHERE host_id=NEW.host_id;
END;
CREATE TRIGGER pwa_task_deleted AFTER DELETE ON planning_tasks BEGIN
    UPDATE pwa_task_versions SET revision=revision+1 WHERE host_id=OLD.host_id;
END;
