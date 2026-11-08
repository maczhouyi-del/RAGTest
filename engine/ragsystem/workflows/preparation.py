"""MVP preparation composes existing fenced tasks, never a second queue/database."""

import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.ipc.directories import Directories
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.pipeline import Parser
from ragsystem.storage.database import utc_now


class Preparation:
    def __init__(self, db, root, search):
        self.db, self.root, self.search, self.jobs = db, root, search, Jobs(db)

    def _versions(self, conn, job):
        payload = json.loads(job["payload_json"])
        if payload.get("action") != "mvp_prepare":
            raise EngineError("IDEMPOTENCY_CONFLICT", status=409)
        if "versions" in payload:  # Existing schema21 intents remain readable.
            return payload["versions"]
        scope = conn.execute("SELECT versions_json FROM scope_snapshots WHERE id=?", (payload["scope_id"],)).fetchone()
        if scope is None or hashlib.sha256(scope[0].encode()).hexdigest() != payload["scope_sha256"]:
            raise EngineError("SCOPE_IDENTITY_CHANGED", status=409)
        return [item["doc_version_id"] for item in json.loads(scope[0])]

    def versions(self, job_id):
        with self.db.connection() as conn:
            return self._versions(conn, self.jobs.get(job_id))

    def enqueue(self, versions, key):
        if not 1 <= len(versions) <= 1000 or len(set(versions)) != len(versions):
            raise EngineError("SCOPE_NOT_AVAILABLE", status=409)
        versions = sorted(versions)
        with self.db.transaction() as conn:
            existing = conn.execute("SELECT * FROM jobs WHERE type='verify' AND idempotency_key=?", (key,)).fetchone()
            if existing:
                if self._versions(conn, existing) != versions:
                    raise EngineError("IDEMPOTENCY_CONFLICT", status=409)
                return dict(existing)
            rows = conn.execute(
                "SELECT id AS doc_version_id,document_id,file_sha256 FROM document_versions WHERE visibility='visible' AND id IN ("
                + ",".join("?" for _ in versions) + ") ORDER BY id", versions
            ).fetchall()
            if len(rows) != len(versions):
                raise EngineError("SCOPE_NOT_AVAILABLE", status=409)
            snapshot = json.dumps([dict(row) for row in rows], sort_keys=True, separators=(",", ":"))
            scope_id = str(uuid4())
            conn.execute("INSERT INTO scope_snapshots VALUES(?,NULL,?,?)", (scope_id, snapshot, utc_now()))
            return self.jobs.enqueue("verify", key, {
                "action": "mvp_prepare", "display_name": "mvp_prepare", "scope_id": scope_id,
                "scope_sha256": hashlib.sha256(snapshot.encode()).hexdigest(),
            }, connection=conn)

    def run(self, job_id, versions):
        job = self.jobs.claim(job_id, lease_seconds=1800)
        if job is None:
            return
        token = job["lease_token"]
        heartbeat = time.monotonic()

        def check(connection=None):
            nonlocal heartbeat
            if connection is not None:
                self.jobs.require_lease(connection, job_id, token)
                return
            with self.db.connection() as conn:
                self.jobs.require_lease(conn, job_id, token)
            if time.monotonic() - heartbeat > 20:
                self.jobs.heartbeat(job_id, token, seconds=1800)
                heartbeat = time.monotonic()

        try:
            failures = []
            for version in versions:
                check()
                with self.db.connection() as conn:
                    row = conn.execute(
                        "SELECT v.visibility,s.page_count FROM document_versions v LEFT JOIN parse_state s ON s.doc_version_id=v.id WHERE v.id=?",
                        (version,),
                    ).fetchone()
                if row is None or row["visibility"] != "visible":
                    raise EngineError("SCOPE_NOT_AVAILABLE")
                if not row["page_count"]:
                    try:
                        Parser(self.db, self.root).parse(
                            version, job_id + ":" + version, parent_check=check
                        )
                    except EngineError as exc:
                        check()
                        failures.append({"version_id": version, "code": exc.code})
            check()
            config = self.search.config()
            if config and not self.search.status()["ready"]:
                queued = self.jobs.enqueue("embed_batch", job_id + ":index", {"parent_id": job_id})
                grant = Directories().issue(Path(config["model_dir"]), "embedding")
                self.search.build(queued["id"], grant, config["backend"], parent_check=check)
                indexed = self.jobs.get(queued["id"])
                if indexed["status"] != "completed":
                    raise EngineError(indexed["error_code"] or "INDEX_BUILD_FAILED")
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job_id, token)
                self.jobs.event(
                    conn,
                    job_id,
                    "mvp_prepared",
                    {
                        "versions": versions,
                        "failures": failures,
                        "index_configured": config is not None,
                    },
                )
            if failures:
                raise EngineError("PREPARATION_PARTIAL")
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job_id, token)
                self.jobs.complete(
                    job_id,
                    token,
                    "mvp_preparation:" + ("indexed" if config else "needs_embedding_model"),
                    connection=conn,
                )
        except Exception as exc:
            self.jobs.fail(
                job_id, token, exc.code if isinstance(exc, EngineError) else "PREPARATION_FAILED"
            )
