CREATE TABLE parse_runs (
    id TEXT PRIMARY KEY,
    doc_version_id TEXT NOT NULL REFERENCES document_versions(id),
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','ready','partial','failed')),
    page_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT
);
CREATE TABLE elements (
    id TEXT PRIMARY KEY,
    parse_run_id TEXT NOT NULL REFERENCES parse_runs(id),
    page_number INTEGER NOT NULL CHECK(page_number>0),
    raw_text TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    error_code TEXT,
    page_rotation_degrees INTEGER NOT NULL CHECK(page_rotation_degrees IN (0,90,180,270)),
    UNIQUE(parse_run_id,page_number)
);
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    doc_version_id TEXT NOT NULL REFERENCES document_versions(id),
    parse_run_id TEXT NOT NULL REFERENCES parse_runs(id),
    element_id TEXT NOT NULL REFERENCES elements(id),
    content_sha256 TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    start_offset INTEGER NOT NULL CHECK(start_offset>=0),
    end_offset INTEGER NOT NULL CHECK(end_offset>start_offset),
    page_number INTEGER NOT NULL CHECK(page_number>0),
    visible INTEGER NOT NULL DEFAULT 0 CHECK(visible IN (0,1))
);
CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id UNINDEXED, clean_text, tokenize='unicode61');
CREATE INDEX chunks_by_version ON chunks(doc_version_id,visible);
CREATE INDEX parse_runs_by_version ON parse_runs(doc_version_id,created_at);
