CREATE TABLE parse_page_structure (
    element_id TEXT PRIMARY KEY REFERENCES elements(id),
    blocks_json TEXT NOT NULL
);
CREATE TABLE parse_tables (
    id TEXT PRIMARY KEY,
    parse_run_id TEXT NOT NULL REFERENCES parse_runs(id),
    doc_version_id TEXT NOT NULL REFERENCES document_versions(id),
    element_id TEXT REFERENCES elements(id),
    page_number INTEGER CHECK(page_number>0),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    source_ref TEXT NOT NULL,
    source_pages_json TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK(row_count>=0),
    column_count INTEGER NOT NULL CHECK(column_count>=0),
    raw_json TEXT NOT NULL,
    UNIQUE(parse_run_id,ordinal)
);
CREATE INDEX tables_by_version ON parse_tables(doc_version_id,parse_run_id,ordinal);
CREATE TABLE table_cells (
    id TEXT PRIMARY KEY,
    table_id TEXT NOT NULL REFERENCES parse_tables(id),
    ordinal INTEGER NOT NULL,
    row_start INTEGER NOT NULL,
    row_end INTEGER NOT NULL CHECK(row_end>row_start),
    column_start INTEGER NOT NULL,
    column_end INTEGER NOT NULL CHECK(column_end>column_start),
    text TEXT NOT NULL,
    column_header INTEGER NOT NULL CHECK(column_header IN (0,1)),
    row_header INTEGER NOT NULL CHECK(row_header IN (0,1)),
    start_offset INTEGER,
    end_offset INTEGER,
    raw_json TEXT NOT NULL,
    CHECK((start_offset IS NULL AND end_offset IS NULL) OR (start_offset>=0 AND end_offset>=start_offset)),
    UNIQUE(table_id,ordinal)
);
CREATE INDEX cells_by_table ON table_cells(table_id,ordinal);
CREATE TABLE table_reviews (
    id TEXT PRIMARY KEY,
    table_id TEXT NOT NULL REFERENCES parse_tables(id),
    revision INTEGER NOT NULL CHECK(revision>0),
    status TEXT NOT NULL CHECK(status IN ('unreviewed','confirmed','rejected','uncertain')),
    note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(table_id,revision)
);
