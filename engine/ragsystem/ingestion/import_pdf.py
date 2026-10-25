import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.ipc.grants import MAX_PDF_BYTES, Grants, digest_stream
from ragsystem.jobs.repository import Jobs
from ragsystem.storage.database import Database, utc_now


class PdfImporter:
    def __init__(self, db: Database, root: Path):
        self.db, self.root, self.jobs = db, Path(root), Jobs(db)
        (self.root / "papers").mkdir(parents=True, exist_ok=True)
        (self.root / "staging").mkdir(parents=True, exist_ok=True)

    def list_documents(self):
        with self.db.connection() as conn:
            return [
                dict(row)
                for row in conn.execute("""SELECT d.id AS document_id,d.title,
                v.id AS doc_version_id,v.file_sha256,v.parse_status,v.created_at,f.size_bytes
                FROM documents d JOIN document_versions v ON v.document_id=d.id
                JOIN file_assets f ON f.sha256=v.file_sha256 WHERE v.visibility='visible'
                ORDER BY v.created_at DESC""")
            ]

    def run(self, job, grant, fault=lambda stage: None):
        token, job_id = job["lease_token"], job["id"]
        temp = self.root / "staging" / (job_id + "-" + str(uuid4()) + ".part")
        try:
            grant.source.seek(0)
            digest, size, last_beat = hashlib.sha256(), 0, time.monotonic()
            with temp.open("xb") as target:
                while data := grant.source.read(1024 * 1024):
                    size += len(data)
                    if size > MAX_PDF_BYTES:
                        raise EngineError("PDF_TOO_LARGE")
                    target.write(data)
                    digest.update(data)
                    if time.monotonic() - last_beat > 5:
                        self.jobs.heartbeat(job_id, token)
                        last_beat = time.monotonic()
                    fault("copy_chunk")
                target.flush()
                os.fsync(target.fileno())
            if digest.hexdigest() != grant.sha256 or size != grant.size:
                raise EngineError("SOURCE_CHANGED", status=409)
            destination = self.root / "papers" / (grant.sha256 + ".pdf")
            # Hard-link publication is create-only and same-filesystem atomic.
            # Keep the staging link: crash evidence is never batch-cleaned.
            try:
                os.link(temp, destination)
            except FileExistsError:
                with destination.open("rb") as existing:
                    actual, actual_size = digest_stream(existing)
                if actual != grant.sha256 or actual_size != size:
                    raise EngineError("OBJECT_CORRUPT", status=409)
            except OSError as exc:
                raise EngineError("FILE_PUBLISH_FAILED", retriable=True) from exc
            if os.name != "nt":
                fd = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            fault("file_published")
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job_id, token)
                existing = conn.execute(
                    "SELECT id,document_id FROM document_versions WHERE file_sha256=?",
                    (grant.sha256,),
                ).fetchone()
                version_id = existing["id"] if existing else str(uuid4())
                if not existing:
                    document_id, stamp = str(uuid4()), utc_now()
                    conn.execute(
                        "INSERT INTO file_assets VALUES(?,?,?,?)",
                        (grant.sha256, size, "papers/" + grant.sha256 + ".pdf", stamp),
                    )
                    conn.execute(
                        "INSERT INTO documents VALUES(?,?,?)",
                        (document_id, grant.display_name, stamp),
                    )
                    conn.execute(
                        "INSERT INTO document_versions(id,document_id,file_sha256,visibility,created_at) VALUES(?,?,?,'visible',?)",
                        (version_id, document_id, grant.sha256, stamp),
                    )
                else:
                    document_id = existing["document_id"]
                project_id = json.loads(job["payload_json"]).get("project_id")
                if project_id is not None:
                    conn.execute(
                        """INSERT INTO project_documents VALUES(?,?,1,?)
                        ON CONFLICT(project_id,document_id) DO UPDATE SET linked=1,
                        updated_at=excluded.updated_at WHERE project_documents.linked=0""",
                        (project_id, document_id, utc_now()),
                    )
                from ragsystem.library.metadata import MetadataExtraction

                MetadataExtraction(self.db, self.root).ensure(version_id, connection=conn)
                fault("before_commit")
                self.jobs.complete(job_id, token, "document_version:" + version_id, connection=conn)
            fault("after_commit")
            return {"doc_version_id": version_id, "file_sha256": grant.sha256}
        except EngineError as exc:
            self.jobs.fail(job_id, token, exc.code)
            raise
        except OSError as exc:
            self.jobs.fail(job_id, token, "FILE_IO_FAILED")
            raise EngineError("FILE_IO_FAILED", retriable=True) from exc
        finally:
            grant.source.close()

    def import_path_for_test(
        self, path: Path, key: str, *, fault=lambda stage: None, project_id=None
    ):
        """In-process test helper; never exposed as a user/IPC path endpoint."""
        grants = Grants()
        grant = grants.issue(Path(path).absolute())
        try:
            job = self.jobs.enqueue(
                "import",
                key,
                {
                    "sha256": grant.sha256,
                    "display_name": grant.display_name,
                    "project_id": project_id,
                },
            )
            if job["status"] == "completed":
                return {
                    "doc_version_id": job["result_ref"].split(":", 1)[1],
                    "file_sha256": grant.sha256,
                }
            # Same process can resume a retained test intent only after fencing
            # its previous lease. Production recovery waits for lease expiry.
            if job["status"] == "running":
                self.jobs.recover_expired(now=job["lease_until"] + 1)
            claimed = self.jobs.claim(job["id"])
            if claimed is None:
                raise EngineError("JOB_NOT_RUNNABLE", status=409)
            return self.run(claimed, grant, fault)
        finally:
            if not grant.source.closed:
                grant.source.close()
            grants.close()

    def recover_published_imports(self):
        """Resume expired imports from retained immutable objects, never source paths."""
        self.jobs.recover_expired()
        recovered = 0
        for job in self.jobs.list():
            if job["type"] != "import" or job["status"] not in {"queued", "retry_wait"}:
                continue
            payload = json.loads(job["payload_json"])
            digest = payload.get("sha256", "")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                continue
            target = self.root / "papers" / (digest + ".pdf")
            if not target.is_file():
                continue  # Original was not published; needs a fresh user grant.
            grants = Grants()
            try:
                grant = grants.issue(target.absolute())
                if isinstance(payload.get("display_name"), str):
                    grant.display_name = payload["display_name"][:255]
                claimed = self.jobs.claim(job["id"])
                if claimed:
                    self.run(claimed, grant)
                    recovered += 1
            finally:
                grants.close()
        return recovered

    def resume(self, job_id):
        job = self.jobs.get(job_id)
        digest = json.loads(job["payload_json"]).get("sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise EngineError("RESELECT_FILE_REQUIRED", status=409)
        path = self.root / "papers" / (digest + ".pdf")
        if not path.is_file():
            raise EngineError("RESELECT_FILE_REQUIRED", status=409)
        grants = Grants()
        grant = grants.issue(path.absolute())
        try:
            grant.display_name = json.loads(job["payload_json"]).get("display_name", path.name)
            claimed = self.jobs.claim(job_id)
            if claimed:
                self.run(claimed, grant)
        finally:
            grant.source.close()
            grants.close()
