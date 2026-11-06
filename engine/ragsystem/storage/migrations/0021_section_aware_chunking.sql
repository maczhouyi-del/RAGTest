CREATE TABLE structure_publications (
 id TEXT PRIMARY KEY REFERENCES parse_runs(id),
 doc_version_id TEXT NOT NULL REFERENCES document_versions(id),
 revision INTEGER NOT NULL,
 config_json TEXT NOT NULL,
 UNIQUE(doc_version_id, revision)
);
CREATE TABLE document_sections (
 id TEXT PRIMARY KEY,
 publication_id TEXT NOT NULL REFERENCES structure_publications(id),
 parent_section_id TEXT REFERENCES document_sections(id),
 section_title TEXT NOT NULL,
 section_level INTEGER NOT NULL,
 section_path TEXT NOT NULL,
 start_page INTEGER NOT NULL,
 end_page INTEGER NOT NULL,
 detection_method TEXT NOT NULL,
 detection_confidence REAL NOT NULL
);
CREATE TABLE document_paragraphs (
 id TEXT PRIMARY KEY,
 publication_id TEXT NOT NULL REFERENCES structure_publications(id),
 element_id TEXT NOT NULL REFERENCES elements(id),
 section_id TEXT REFERENCES document_sections(id),
 page_number INTEGER NOT NULL,
 start_offset INTEGER NOT NULL,
 end_offset INTEGER NOT NULL,
 content_type TEXT NOT NULL,
 fallback_reason TEXT
);
CREATE TABLE chunk_structure (
 publication_id TEXT NOT NULL REFERENCES structure_publications(id),
 chunk_id TEXT NOT NULL REFERENCES chunks(id),
 paragraph_id TEXT REFERENCES document_paragraphs(id),
 section_id TEXT REFERENCES document_sections(id),
 fallback_reason TEXT,
 PRIMARY KEY(publication_id,chunk_id)
);
CREATE INDEX chunk_structure_chunk ON chunk_structure(chunk_id);
CREATE INDEX sections_publication ON document_sections(publication_id);
CREATE INDEX chunks_by_element_offsets ON chunks(element_id, start_offset);
