import hashlib
import json
import struct
import time
from pathlib import Path
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.indexing.embeddings import Embeddings
from ragsystem.indexing.incremental import embed_visible
from ragsystem.jobs.repository import Jobs
from ragsystem.models.local_onnx import LocalE5
from ragsystem.retrieval.metadata_scope import require_metadata_scope
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.database import utc_now


class HybridSearch:
    def __init__(self, db, root):
        self.db, self.root = db, Path(root)
        self.encoder, self.encoder_path = None, None
        self.sources, self.cache, self.jobs = Sources(db, root), Embeddings(db), Jobs(db)

    def chunks(self, conn):
        return [
            tuple(row)
            for row in conn.execute("""SELECT c.id,c.content_sha256,c.doc_version_id
            FROM chunks c JOIN document_versions v ON v.id=c.doc_version_id
            WHERE c.visible=1 AND v.visibility='visible' ORDER BY c.id""")
        ]

    def fingerprint(self, conn):
        return hashlib.sha256(json.dumps(self.chunks(conn)).encode()).hexdigest()

    def config(self):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT value_json FROM app_settings WHERE key='active_index'"
            ).fetchone()
            return json.loads(row[0]) if row else None

    def status(self):
        config = self.config()
        with self.db.connection() as conn:
            count = len(self.chunks(conn))
            current = self.fingerprint(conn)
        return {
            "configured": bool(config),
            "ready": bool(
                config
                and config["chunk_fingerprint"] == current
                and (self.root / config["relative_path"]).exists()
            ),
            "visible_chunks": count,
            "backend": config["backend"] if config else None,
            "model": config["fingerprint"]["model"] if config else None,
            "indexed_chunks": config["chunks"] if config else 0,
            "generation": config["generation"] if config else None,
            "candidate_only": True,
        }

    def adapter(self, backend, path, space, dimension):
        if backend == "sqlite-vec":
            from ragsystem.vector_adapters.sqlite_vec import SQLiteVec

            return SQLiteVec(path, space, dimension)
        if backend == "lancedb":
            from ragsystem.vector_adapters.lancedb import LanceDB

            return LanceDB(path, space, dimension)
        raise EngineError("VECTOR_BACKEND_INVALID")

    def build(self, job_id, directory, backend):
        job = self.jobs.claim(job_id, lease_seconds=1800)
        if not job:
            return
        token = job["lease_token"]

        def progress(current, total):
            directory.check()
            self.jobs.heartbeat(job_id, token, seconds=1800)

        try:
            with self.db.connection() as conn:
                expected = self.fingerprint(conn)
                if not self.chunks(conn):
                    raise EngineError("NO_PARSED_DOCUMENTS")
            try:
                encoder = LocalE5(directory.path)
            except ImportError as exc:
                raise EngineError("MODEL_RUNTIME_NOT_PACKAGED") from exc
            progress(0, 1)
            result = embed_visible(self.db, encoder, progress=progress)
            space, generation = result["space_id"], str(uuid4())
            relative = (
                "vectors/" + generation + ("/index.db" if backend == "sqlite-vec" else "/lance")
            )
            adapter = self.adapter(backend, self.root / relative, space, encoder.dimension)
            with self.db.connection() as conn:
                entries = [
                    (
                        row["id"],
                        list(struct.unpack("<" + "f" * encoder.dimension, row["vector_bytes"])),
                    )
                    for row in conn.execute(
                        "SELECT * FROM embedding_records WHERE space_id=? ORDER BY id", (space,)
                    )
                ]
            adapter.upsert(entries)
            if not adapter.check_integrity([item[0] for item in entries])["ok"]:
                raise EngineError("INDEX_INCOMPLETE")
            progress(1, 1)
            config = {
                **result,
                "generation": generation,
                "backend": backend,
                "relative_path": relative,
                "model_dir": str(directory.path),
                "fingerprint": encoder.fingerprint,
                "chunk_fingerprint": expected,
            }
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job_id, token)
                if self.fingerprint(conn) != expected:
                    raise EngineError("INDEX_SCOPE_CHANGED")
                conn.execute(
                    "INSERT INTO index_generations VALUES(?,?,?,?,?,?)",
                    (generation, backend, space, relative, expected, utc_now()),
                )
                conn.execute(
                    "INSERT INTO app_settings VALUES('active_index',?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                    (json.dumps(config), utc_now()),
                )
                self.jobs.complete(job_id, token, "index_generation:" + generation, connection=conn)
            self.encoder, self.encoder_path = encoder, str(directory.path)
        except Exception as exc:
            self.jobs.fail(
                job_id, token, exc.code if isinstance(exc, EngineError) else "INDEX_BUILD_FAILED"
            )

    def paper_quota(self, hits, k, quota):
        if quota is None:
            return hits[:k]
        if type(quota) is not int or not 1 <= quota <= 10:
            raise EngineError("INVALID_SEARCH")
        if not hits:
            return []
        versions = list(dict.fromkeys(hit["doc_version_id"] for hit in hits))
        with self.db.connection() as conn:
            papers = {
                row["id"]: row["document_id"]
                for row in conn.execute(
                    "SELECT id,document_id FROM document_versions WHERE visibility='visible' AND id IN ("
                    + ",".join("?" for _ in versions)
                    + ")",
                    versions,
                )
            }
        counts, chosen = {}, []
        for hit in hits:
            paper = papers.get(hit["doc_version_id"])
            if paper is None or counts.get(paper, 0) >= quota:
                continue
            counts[paper] = counts.get(paper, 0) + 1
            chosen.append(hit)
            if len(chosen) == k:
                break
        return chosen

    def search(self, query, versions, k, project_id, strategy, paper_quota=None, filters=None):
        require_metadata_scope(self.db, versions, filters)
        if strategy in {"vector_exact", "hybrid"} and not self.config():
            raise EngineError("EMBEDDING_NOT_CONFIGURED", status=409)
        lexical = self.sources.search(
            query, versions, max(k, 50), project_id=project_id, terms=strategy != "fts_only"
        )
        if strategy in {"fts_only", "keyword"}:
            require_metadata_scope(self.db, versions, filters)
            return {
                "results": self.paper_quota(lexical, k, paper_quota),
                "per_paper_limit": paper_quota,
                "strategy": strategy,
                "tokenizer_version": "cjk-bigrams-latin-v1"
                if strategy == "keyword"
                else "unicode61-literal",
            }
        config = self.config()
        if not config:
            raise EngineError("EMBEDDING_NOT_CONFIGURED", status=409)
        if not self.status()["ready"]:
            raise EngineError("INDEX_REBUILD_REQUIRED", status=409)
        if self.encoder is None or self.encoder_path != config["model_dir"]:
            try:
                self.encoder = LocalE5(Path(config["model_dir"]))
            except (ImportError, OSError) as exc:
                raise EngineError("MODEL_NOT_AVAILABLE", status=409) from exc
            self.encoder_path = config["model_dir"]
        if self.encoder.fingerprint != config["fingerprint"]:
            raise EngineError("MODEL_FINGERPRINT_CHANGED", status=409)
        started = time.perf_counter()
        query_vector = self.encoder.encode([query], query=True)[0]
        encoding_ms = (time.perf_counter() - started) * 1000
        eligible = self.cache.eligible(config["space_id"], versions)
        adapter = self.adapter(
            config["backend"],
            self.root / config["relative_path"],
            config["space_id"],
            self.encoder.dimension,
        )
        hits = adapter.search_exact(query_vector, eligible, max(k, 50))
        vector_hits = []
        with self.db.connection() as conn:
            conn.execute("BEGIN")
            # Recheck project visibility after potentially slow query encoding.
            if project_id is not None:
                actual = {
                    row[0]
                    for row in conn.execute(
                        """SELECT v.id FROM document_versions v
                    JOIN project_documents pd ON pd.document_id=v.document_id
                    WHERE pd.project_id=? AND pd.linked=1 AND v.visibility='visible'""",
                        (project_id,),
                    )
                }
                if not set(versions).issubset(actual):
                    raise EngineError("SCOPE_NOT_AVAILABLE", status=409)
            for hit in hits:
                rows = conn.execute(
                    f"""SELECT c.* FROM chunks c JOIN chunk_embedding_links l ON l.chunk_id=c.id
                    JOIN document_versions v ON v.id=c.doc_version_id WHERE l.embedding_id=? AND c.visible=1
                    AND v.visibility='visible' AND v.id IN ({",".join("?" for _ in versions)}) ORDER BY c.id""",
                    [hit["embedding_id"], *versions],
                ).fetchall()
                for row in rows:
                    vector_hits.append(
                        {
                            "doc_version_id": row["doc_version_id"],
                            "chunk_id": row["id"],
                            "source_anchor_id": row["id"],
                            "page_number": row["page_number"],
                            "preview": row["clean_text"][:1000],
                            "rank": len(vector_hits) + 1,
                            "location_confidence": "unknown",
                            "distance": hit["distance"],
                        }
                    )
        if strategy == "vector_exact":
            results = vector_hits
        else:
            scores, items = {}, {}
            for group in [lexical, vector_hits]:
                for rank, hit in enumerate(group):
                    identifier = hit["chunk_id"]
                    scores[identifier] = scores.get(identifier, 0) + 1 / (60 + rank + 1)
                    items[identifier] = hit
            results = [
                items[identifier] | {"rrf_score": scores[identifier]}
                for identifier in sorted(scores, key=lambda i: (-scores[i], i))
            ]
        require_metadata_scope(self.db, versions, filters)
        with self.db.connection() as conn:
            visible = {
                row[0]
                for row in conn.execute(
                    "SELECT id FROM document_versions WHERE visibility='visible' AND id IN ("
                    + ",".join("?" for _ in versions)
                    + ")",
                    versions,
                )
            }
            if visible != set(versions):
                raise EngineError("SCOPE_NOT_AVAILABLE", status=409)
        results = self.paper_quota(results, k, paper_quota)
        return {
            "per_paper_limit": paper_quota,
            "results": [hit | {"rank": index + 1} for index, hit in enumerate(results)],
            "strategy": strategy,
            "query_embedding_ms": encoding_ms,
            "generation": config["generation"],
            "scientific_quality": "NOT_EVALUATED",
        }
