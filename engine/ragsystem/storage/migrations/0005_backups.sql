CREATE TABLE backup_records (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('backup','restored')),
    local_path TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    document_count INTEGER NOT NULL,
    embedding_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
