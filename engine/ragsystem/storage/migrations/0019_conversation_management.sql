ALTER TABLE conversations ADD COLUMN archived_at TEXT;
ALTER TABLE conversations ADD COLUMN renamed_at TEXT;
CREATE INDEX conversations_archive_activity ON conversations(project_id,archived_at,updated_at DESC,id DESC);
