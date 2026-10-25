CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE project_documents (
    project_id TEXT NOT NULL REFERENCES projects(id),
    document_id TEXT NOT NULL REFERENCES documents(id),
    linked INTEGER NOT NULL CHECK(linked IN (0,1)),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(project_id,document_id)
);
CREATE TABLE document_metadata (
    document_id TEXT PRIMARY KEY REFERENCES documents(id),
    authors_json TEXT NOT NULL DEFAULT '[]',
    publication_year INTEGER,
    doi TEXT,
    venue TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    revision INTEGER NOT NULL CHECK(revision>=1),
    origin TEXT NOT NULL CHECK(origin='manual'),
    updated_at TEXT NOT NULL
);
CREATE INDEX metadata_doi ON document_metadata(doi) WHERE doi IS NOT NULL;
CREATE INDEX project_documents_document ON project_documents(document_id,linked);
