CREATE TABLE generation_provider_authorizations (
 provider_id TEXT PRIMARY KEY REFERENCES generation_providers(id),
 provider_revision INTEGER NOT NULL CHECK(provider_revision>0),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 updated_at TEXT NOT NULL
);
