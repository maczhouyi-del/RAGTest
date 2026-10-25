CREATE TABLE document_lifecycle (
    document_id TEXT PRIMARY KEY REFERENCES documents(id),
    state TEXT NOT NULL CHECK(state IN ('active','archived','retracted')),
    revision INTEGER NOT NULL CHECK(revision>0),
    note TEXT NOT NULL,
    visibility_snapshot_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE lifecycle_revisions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    revision INTEGER NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(document_id,revision)
);
CREATE INDEX events_kind_job ON events(kind,job_id,id);
CREATE INDEX answers_history_order ON answer_runs(created_at DESC,id DESC);
CREATE INDEX research_history_order ON research_plans(created_at DESC,id DESC);
