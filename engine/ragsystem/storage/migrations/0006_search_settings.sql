CREATE TABLE app_settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE index_generations (
    id TEXT PRIMARY KEY,
    backend TEXT NOT NULL CHECK(backend IN ('sqlite-vec','lancedb')),
    space_id TEXT NOT NULL REFERENCES embedding_spaces(id),
    relative_path TEXT NOT NULL UNIQUE,
    chunk_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE chunks_terms_v1 USING fts5(chunk_id UNINDEXED, terms, tokenize='unicode61');
CREATE TABLE terms_indexed_chunks (chunk_id TEXT PRIMARY KEY REFERENCES chunks(id));
