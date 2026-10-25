ALTER TABLE conversations ADD COLUMN updated_at TEXT;
UPDATE conversations SET updated_at=COALESCE((SELECT MAX(created_at) FROM answer_runs WHERE conversation_id=conversations.id),created_at);
CREATE INDEX conversations_activity ON conversations(project_id,updated_at DESC,id DESC);
CREATE INDEX conversation_turns ON answer_runs(conversation_id,created_at DESC,id DESC);
