CREATE TABLE embedding_spaces (
    id TEXT PRIMARY KEY,
    fingerprint_json TEXT NOT NULL UNIQUE,
    dimension INTEGER NOT NULL CHECK(dimension>0),
    created_at TEXT NOT NULL
);
CREATE TABLE embedding_records (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL REFERENCES embedding_spaces(id),
    content_sha256 TEXT NOT NULL,
    vector_bytes BLOB NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(space_id,content_sha256)
);
CREATE TABLE chunk_embedding_links (
    chunk_id TEXT NOT NULL REFERENCES chunks(id),
    embedding_id TEXT NOT NULL REFERENCES embedding_records(id),
    PRIMARY KEY(chunk_id,embedding_id)
);
