CREATE TABLE generation_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('api','magpie')),
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision>0),
    updated_at TEXT NOT NULL
);
