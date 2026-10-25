CREATE TABLE parse_state (
    doc_version_id TEXT PRIMARY KEY REFERENCES document_versions(id),
    revision INTEGER NOT NULL CHECK(revision>0),
    page_count INTEGER NOT NULL CHECK(page_count>0),
    last_parse_run_id TEXT NOT NULL REFERENCES parse_runs(id),
    unlocated_items INTEGER NOT NULL DEFAULT 0 CHECK(unlocated_items>=0)
);
CREATE TABLE published_pages (
    doc_version_id TEXT NOT NULL REFERENCES document_versions(id),
    page_number INTEGER NOT NULL CHECK(page_number>0),
    element_id TEXT NOT NULL UNIQUE REFERENCES elements(id),
    PRIMARY KEY(doc_version_id,page_number)
);
CREATE TABLE published_tables (
    table_id TEXT PRIMARY KEY REFERENCES parse_tables(id),
    doc_version_id TEXT NOT NULL REFERENCES document_versions(id)
);
CREATE TABLE parse_attempts (
    id TEXT PRIMARY KEY,
    parse_run_id TEXT NOT NULL REFERENCES parse_runs(id),
    method TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
    page_numbers_json TEXT,
    error_code TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX attempts_by_parse ON parse_attempts(parse_run_id,created_at,id);
INSERT INTO parse_state SELECT r.doc_version_id,1,r.page_count,r.id,COALESCE((SELECT MAX(json_extract(e.details_json,'$.unresolved_items')) FROM events e WHERE e.kind='parser_result' AND json_extract(e.details_json,'$.parse_run_id')=r.id),0) FROM parse_runs r WHERE r.status IN ('ready','partial') AND r.page_count>0 AND NOT EXISTS(SELECT 1 FROM parse_runs n WHERE n.doc_version_id=r.doc_version_id AND n.status IN ('ready','partial') AND (COALESCE(n.finished_at,n.created_at)>COALESCE(r.finished_at,r.created_at) OR (COALESCE(n.finished_at,n.created_at)=COALESCE(r.finished_at,r.created_at) AND n.id>r.id)));
INSERT INTO published_pages SELECT s.doc_version_id,e.page_number,e.id FROM parse_state s JOIN elements e ON e.parse_run_id=s.last_parse_run_id;
INSERT INTO published_tables SELECT t.id,t.doc_version_id FROM parse_tables t JOIN parse_state s ON s.last_parse_run_id=t.parse_run_id;
