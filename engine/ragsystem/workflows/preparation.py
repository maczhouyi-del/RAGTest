"""MVP preparation composes existing fenced tasks, never a second queue/database."""

import time
from pathlib import Path

from ragsystem.domain.errors import EngineError
from ragsystem.ipc.directories import Directories
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.pipeline import Parser


class Preparation:
    def __init__(self, db, root, search):
        self.db, self.root, self.search, self.jobs = db, root, search, Jobs(db)

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
