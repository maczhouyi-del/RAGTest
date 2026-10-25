CREATE VIRTUAL TABLE chunks_terms_v2 USING fts5(chunk_id UNINDEXED, terms, tokenize='unicode61');
CREATE TABLE terms_indexed_chunks_v2 (chunk_id TEXT PRIMARY KEY REFERENCES chunks(id));
