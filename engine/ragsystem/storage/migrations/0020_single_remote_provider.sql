ALTER TABLE generation_providers ADD COLUMN retired_at TEXT;
UPDATE generation_providers SET retired_at=strftime('%Y-%m-%dT%H:%M:%f+00:00','now') WHERE id != (SELECT id FROM generation_providers ORDER BY updated_at DESC,id ASC LIMIT 1);
UPDATE generation_provider_authorizations SET enabled=0 WHERE provider_id IN (SELECT id FROM generation_providers WHERE retired_at IS NOT NULL);
CREATE UNIQUE INDEX one_active_remote_provider ON generation_providers((1)) WHERE retired_at IS NULL;
