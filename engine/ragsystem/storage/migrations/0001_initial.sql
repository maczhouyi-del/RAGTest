CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
CREATE TABLE file_assets (
    sha256 TEXT PRIMARY KEY CHECK(length(sha256)=64),
    size_bytes INTEGER NOT NULL CHECK(size_bytes>0),
    relative_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE document_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    file_sha256 TEXT NOT NULL UNIQUE REFERENCES file_assets(sha256),
    visibility TEXT NOT NULL CHECK(visibility IN ('visible','hidden')),
    parse_status TEXT NOT NULL DEFAULT 'not_started',
    created_at TEXT NOT NULL
);
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('import','parse_page','embed_batch','index_upsert','verify','research_extract','backup')),
    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','retry_wait','cancelling','cancelled')),
    idempotency_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count>=0),
    max_attempts INTEGER NOT NULL CHECK(max_attempts>0 AND attempt_count<=max_attempts),
    lease_until REAL,
    lease_token TEXT,
    heartbeat_at REAL,
    result_ref TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(type,idempotency_key),
    CHECK(status!='completed' OR length(result_ref)>0)
);
CREATE TABLE job_attempts (
    job_id TEXT NOT NULL REFERENCES jobs(id),
    attempt INTEGER NOT NULL,
    lease_token TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    outcome TEXT,
    PRIMARY KEY(job_id,attempt)
);
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    kind TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX jobs_pending ON jobs(status,lease_until);
