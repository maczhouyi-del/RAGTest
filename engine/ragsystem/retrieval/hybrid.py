import hashlib
import json
import sqlite3
import struct
import time
from pathlib import Path
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.indexing.embeddings import Embeddings
from ragsystem.indexing.incremental import embed_visible
from ragsystem.indexing.integrity import checked_path, manifest, stamp
from ragsystem.jobs.repository import Jobs
from ragsystem.models.local_onnx import LocalE5
from ragsystem.retrieval.metadata_scope import require_metadata_scope
from ragsystem.retrieval.source_search import Sources
from ragsystem.retrieval.tokenizer import TOKENIZER_VERSION
from ragsystem.storage.database import utc_now


class HybridSearch:
    def __init__(self, db, root):
        self.db, self.root = db, Path(root)
        self.encoder, self.encoder_path = None, None
        self._integrity_cache = None
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
        ready, reason = False, "EMBEDDING_NOT_CONFIGURED"
        if config:
            reason = "INDEX_REBUILD_REQUIRED"
            try:
                if config["chunk_fingerprint"] == current and config.get("index_manifest"):
                    path = checked_path(self.root, config["relative_path"])
                    signature = (config["generation"], stamp(path))
                    if self._integrity_cache != signature:
                        if manifest(path) != config["index_manifest"]:
                            raise EngineError("INDEX_INVALID")
                        self._integrity_cache = signature
                    ready = True
                    reason = None
            except (EngineError, OSError, ValueError, KeyError, sqlite3.DatabaseError):
                reason = "INDEX_INVALID"
        return {
            "configured": bool(config),
            "ready": ready,
            "reason": reason,
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

    def build(self, job_id, directory, backend, *, parent_check=None):
        job = self.jobs.claim(job_id, lease_seconds=1800)
        if not job:
            return
        token = job["lease_token"]

        def progress(current, total):
            if parent_check:
                parent_check()
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
                "index_manifest": manifest(checked_path(self.root, relative)),
            }
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job_id, token)
                if parent_check:
                    parent_check(conn)
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
        if quota is not None and (type(quota) is not int or not 1 <= quota <= 10):
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
        # First spend context on distinct content; keep every source association,
        # and use deferred duplicate occurrences if the remaining slots allow it.
        unique, repeated, groups = [], [], {}
        seen_chunks = set()
        for hit in hits:
            if hit["chunk_id"] in seen_chunks:
                continue
            seen_chunks.add(hit["chunk_id"])
            digest = hit.get("content_sha256", hit["chunk_id"])
            (repeated if digest in groups else unique).append(hit)
            associations = hit.get("content_sources") or [
                {
                    key: hit[key]
                    for key in ("chunk_id", "doc_version_id", "source_anchor_id", "page_number")
                    if key in hit
                }
            ]
            group = groups.setdefault(digest, [])
            for source in associations:
                if not any(item["chunk_id"] == source["chunk_id"] for item in group):
                    group.append(source)
        counts, chosen = {}, []
        for hit in unique + repeated:
            paper = papers.get(hit["doc_version_id"])
            if paper is None or (quota is not None and counts.get(paper, 0) >= quota):
                continue
            counts[paper] = counts.get(paper, 0) + 1
            chosen.append(
                hit | {"content_sources": groups[hit.get("content_sha256", hit["chunk_id"])]}
            )
            if len(chosen) == k:
                break
        return chosen

    @staticmethod
    def fuse(lexical, vector):
        items, ranks = {}, {}
        for channel, group in (("lexical_rank", lexical), ("vector_rank", vector)):
            for hit in group:
                key = hit["chunk_id"]
                rank = hit[channel]
                items[key] = items.get(key, {}) | hit
                previous = ranks.setdefault(key, {}).get(channel)
                ranks[key][channel] = min(previous, rank) if previous else rank
        scores = {
            key: sum(1 / (60 + rank) for rank in values.values()) for key, values in ranks.items()
        }
        return [
            items[key] | ranks[key] | {"rrf_score": scores[key]}
            for key in sorted(scores, key=lambda key: (-scores[key], key))
        ]

    def search(
        self,
        query,
        versions,
        k,
        project_id,
        strategy,
        paper_quota=None,
        filters=None,
        *,
        include_candidates=False,
    ):
        if (
            type(k) is not int
            or not 1 <= k <= 100
            or not isinstance(query, str)
            or not query.strip()
            or len(query) > 20000
            or not 1 <= len(versions) <= 1000
            or strategy not in {"fts_only", "keyword", "vector_exact", "hybrid"}
        ):
            raise EngineError("INVALID_SEARCH")
        versions = list(dict.fromkeys(versions))
        search_started = time.perf_counter()
        timings = {}
        if strategy in {"vector_exact", "hybrid"} and not self.config():
            raise EngineError("EMBEDDING_NOT_CONFIGURED", status=409)
        with self.db.connection() as conn:
            self.sources.require_scope(conn, versions, project_id)
        require_metadata_scope(self.db, versions, filters)
        timings["scope_validation_ms"] = (time.perf_counter() - search_started) * 1000
        candidate_limit = max(k, 50)
        phase_started = time.perf_counter()
        lexical = (
            self.sources.search(
                query,
                versions,
                candidate_limit,
                project_id=project_id,
                terms=strategy != "fts_only",
            )
            if strategy != "vector_exact"
            else []
        )
        lexical = [hit | {"lexical_rank": hit["rank"]} for hit in lexical]
        if strategy != "vector_exact":
            timings["lexical_ms"] = (time.perf_counter() - phase_started) * 1000
        if strategy in {"fts_only", "keyword"}:
            require_metadata_scope(self.db, versions, filters)
            phase_started = time.perf_counter()
            selected = self.paper_quota(lexical, k, paper_quota)
            timings["context_selection_ms"] = (time.perf_counter() - phase_started) * 1000
            timings["total_ms"] = (time.perf_counter() - search_started) * 1000
            return {
                "results": [hit | {"rank": index + 1} for index, hit in enumerate(selected)],
                "per_paper_limit": paper_quota,
                "strategy": strategy,
                "candidate_limit_per_channel": candidate_limit,
                "candidate_counts": {"lexical": len(lexical), "vector_embeddings": 0},
                "tokenizer_version": TOKENIZER_VERSION
                if strategy == "keyword"
                else "unicode61-literal",
                **({"candidates": lexical} if include_candidates else {}),
                "timings_ms": timings,
            }
        config = self.config()
        if not config:
            raise EngineError("EMBEDDING_NOT_CONFIGURED", status=409)
        if not self.status()["ready"]:
            raise EngineError("INDEX_REBUILD_REQUIRED", status=409)
        phase_started = time.perf_counter()
        if self.encoder is None or self.encoder_path != config["model_dir"]:
            try:
                self.encoder = LocalE5(Path(config["model_dir"]))
            except (ImportError, OSError) as exc:
                raise EngineError("MODEL_NOT_AVAILABLE", status=409) from exc
            self.encoder_path = config["model_dir"]
        if self.encoder.fingerprint != config["fingerprint"]:
            raise EngineError("MODEL_FINGERPRINT_CHANGED", status=409)
        timings["model_ready_ms"] = (time.perf_counter() - phase_started) * 1000
        started = time.perf_counter()
        query_vector = self.encoder.encode([query], query=True)[0]
        encoding_ms = (time.perf_counter() - started) * 1000
        timings["query_embedding_ms"] = encoding_ms
        phase_started = time.perf_counter()
        eligible = self.cache.eligible(config["space_id"], versions)
        adapter = self.adapter(
            config["backend"],
            self.root / config["relative_path"],
            config["space_id"],
            self.encoder.dimension,
        )
        hits = adapter.search_exact(query_vector, eligible, candidate_limit)
        timings["vector_retrieval_ms"] = (time.perf_counter() - phase_started) * 1000
        vector_hits = []
        phase_started = time.perf_counter()
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
            for vector_rank, hit in enumerate(hits, 1):
                if hit["embedding_id"] not in eligible:
                    raise EngineError("INDEX_INCOMPLETE", status=409)
                rows = conn.execute(
                    f"""SELECT c.* FROM chunks c JOIN chunk_embedding_links l ON l.chunk_id=c.id
                    JOIN embedding_records e ON e.id=l.embedding_id
                    JOIN document_versions v ON v.id=c.doc_version_id WHERE l.embedding_id=? AND e.space_id=?
                    AND e.content_sha256=c.content_sha256 AND c.visible=1
                    AND v.visibility='visible' AND v.id IN ({",".join("?" for _ in versions)}) ORDER BY c.id""",
                    [hit["embedding_id"], config["space_id"], *versions],
                ).fetchall()
                if not rows:
                    raise EngineError("INDEX_INCOMPLETE", status=409)
                for row in rows:
                    vector_hits.append(
                        {
                            "doc_version_id": row["doc_version_id"],
                            "chunk_id": row["id"],
                            "source_anchor_id": row["id"],
                            "page_number": row["page_number"],
                            "preview": row["clean_text"],
                            "rank": vector_rank,
                            "vector_rank": vector_rank,
                            "content_sha256": row["content_sha256"],
                            "location_confidence": "unknown",
                            "distance": hit["distance"],
                        }
                    )
        timings["source_mapping_ms"] = (time.perf_counter() - phase_started) * 1000
        phase_started = time.perf_counter()
        if strategy == "vector_exact":
            results = sorted(vector_hits, key=lambda hit: (hit["vector_rank"], hit["chunk_id"]))
        else:
            results = self.fuse(lexical, vector_hits)
        timings["fusion_ms"] = (time.perf_counter() - phase_started) * 1000
        require_metadata_scope(self.db, versions, filters)
        with self.db.connection() as conn:
            conn.execute("BEGIN")
            self.sources.require_scope(conn, versions, project_id)
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
            active = conn.execute(
                "SELECT value_json FROM app_settings WHERE key='active_index'"
            ).fetchone()
            if (
                not active
                or json.loads(active[0])["generation"] != config["generation"]
                or self.fingerprint(conn) != config["chunk_fingerprint"]
            ):
                raise EngineError("INDEX_SCOPE_CHANGED", status=409)
        if not self.status()["ready"]:
            raise EngineError("INDEX_REBUILD_REQUIRED", status=409)
        candidates = results
        phase_started = time.perf_counter()
        results = self.paper_quota(candidates, k, paper_quota)
        timings["context_selection_ms"] = (time.perf_counter() - phase_started) * 1000
        timings["total_ms"] = (time.perf_counter() - search_started) * 1000
        return {
            "per_paper_limit": paper_quota,
            "results": [hit | {"rank": index + 1} for index, hit in enumerate(results)],
            "strategy": strategy,
            "candidate_limit_per_channel": candidate_limit,
            "candidate_counts": {
                "lexical": len(lexical),
                "vector_embeddings": len(hits),
                "vector_chunks": len(vector_hits),
            },
            "query_embedding_ms": encoding_ms,
            "generation": config["generation"],
            "scientific_quality": "NOT_EVALUATED",
            "timings_ms": timings,
            **({"candidates": candidates} if include_candidates else {}),
        }
