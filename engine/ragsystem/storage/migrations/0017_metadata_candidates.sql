ALTER TABLE document_metadata ADD COLUMN abstract TEXT NOT NULL DEFAULT '';
ALTER TABLE document_metadata ADD COLUMN field_origins_json TEXT NOT NULL DEFAULT '{"title":"manual","authors":"manual","year":"manual","venue":"manual","doi":"manual","abstract":"manual"}';
CREATE TABLE metadata_candidates (
 id TEXT PRIMARY KEY,
 document_id TEXT NOT NULL REFERENCES documents(id),
 doc_version_id TEXT NOT NULL REFERENCES document_versions(id),
 field_name TEXT NOT NULL CHECK(field_name IN ('title','authors','year','venue','doi','abstract')),
 candidate_value TEXT NOT NULL,
 extraction_method TEXT NOT NULL,
 source_page INTEGER,
 source_excerpt TEXT,
 extractor_version TEXT NOT NULL,
 review_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK(review_status IN ('unreviewed','accepted','confirmed')),
 created_at TEXT NOT NULL,
 UNIQUE(doc_version_id,field_name,extractor_version)
);
CREATE INDEX metadata_candidate_document ON metadata_candidates(document_id,doc_version_id,field_name);
