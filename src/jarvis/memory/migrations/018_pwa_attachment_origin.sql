-- Sticky provenance: local uploads cannot become remotely readable through a PWA conversation.
ALTER TABLE conversations ADD COLUMN attachment_device_id TEXT;
