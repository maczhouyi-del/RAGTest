ALTER TABLE generation_providers ADD COLUMN vendor TEXT NOT NULL DEFAULT 'custom' CHECK(vendor IN ('custom','deepseek','openai','magpie'));
ALTER TABLE generation_providers ADD COLUMN auth_mode TEXT NOT NULL DEFAULT 'bearer' CHECK(auth_mode IN ('bearer','none'));
ALTER TABLE generation_providers ADD COLUMN output_mode TEXT NOT NULL DEFAULT 'json_object' CHECK(output_mode IN ('json_object','prompt_json'));
ALTER TABLE generation_providers ADD COLUMN token_parameter TEXT NOT NULL DEFAULT 'max_tokens' CHECK(token_parameter IN ('max_tokens','max_completion_tokens','none'));
UPDATE generation_providers SET vendor='magpie' WHERE kind='magpie';
