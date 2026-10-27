import json
import time
from pathlib import Path
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.ipc.directories import directory_identity
from ragsystem.jobs.repository import Jobs
from ragsystem.storage.backup import Backups
from ragsystem.storage.backup_operations import MARKER, BackupOperations
from ragsystem.storage.database import utc_now


class BackupService:
    def __init__(self, db, root):
        self.db, self.root, self.jobs = db, Path(root), Jobs(db)
        self.operations = BackupOperations(db, root)

    def records(self):
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM backup_records ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        return [
            {
                key: row[key]
                for key in (
                    "id",
                    "kind",
                    "document_count",
                    "embedding_count",
                    "created_at",
                    "manifest_sha256",
                )
            }
            | {"label": Path(row["local_path"]).name}
            for row in rows
        ]

    def run(self, job_id, parent, source=None):
        job = self.jobs.claim(job_id, lease_seconds=1800)
        if job is None:
            return
        token, identifier, last_beat = job["lease_token"], str(uuid4()), 0

        def progress(current, total):
            nonlocal last_beat
            parent.check()
            if source:
                source.check()
            with self.db.connection() as conn:
                self.jobs.require_lease(conn, job_id, token)
            if time.monotonic() - last_beat >= 3:
                self.jobs.heartbeat(job_id, token, seconds=1800)
                last_beat = time.monotonic()

        operation = None
        try:
            operation = self.operations.begin(
                "restored" if source else "backup", parent.path, job_id, identifier
            )
            if source:
                path = parent.path / ("ragsystem-restored-" + identifier)
                inspected = Backups.inspect(source.path, progress=progress)
                Backups.restore(
                    source.path, path, progress=progress, operation=(self.operations, operation)
                )
                (path / "workspace-identity.json").write_text(
                    json.dumps({"restore_id": identifier}) + "\n"
                )
                kind = "restored"
            else:
                path = Backups(self.db, self.root).create(
                    parent.path, progress=progress, operation=(self.operations, operation)
                )
                inspected = Backups.inspect(path, progress=progress, allow_incomplete=True)
                kind = "backup"
            self.operations.complete(operation)
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job_id, token)
                conn.execute(
                    "INSERT INTO backup_records VALUES(?,?,?,?,?,?,?)",
                    (
                        identifier,
                        kind,
                        str(path),
                        inspected["manifest_sha256"],
                        inspected["document_count"],
                        inspected["embedding_count"],
                        utc_now(),
                    ),
                )
                self.jobs.complete(job_id, token, "backup_record:" + identifier, connection=conn)
        except Exception as exc:
            code = exc.code if isinstance(exc, EngineError) else "BACKUP_IO_FAILED"
            if operation is not None:
                operation["state"] = "active"
                if not self.operations.quarantine(operation, code):
                    code = "BACKUP_RECOVERY_REQUIRED"
            self.jobs.fail(job_id, token, code)

    def restored_path(self, identifier):
        with self.db.connection() as conn:
            running = conn.execute(
                "SELECT 1 FROM jobs WHERE status IN ('queued','running','retry_wait') LIMIT 1"
            ).fetchone()
            row = conn.execute(
                "SELECT * FROM backup_records WHERE id=? AND kind='restored'", (identifier,)
            ).fetchone()
        if running:
            raise EngineError("WORKER_BUSY", status=409)
        if not row:
            raise EngineError("NOT_FOUND", status=404)
        path = Path(row["local_path"])
        directory_identity(path)
        try:
            if path.name != "ragsystem-restored-" + identifier or any(
                (path / name).is_symlink()
                for name in ("workspace-identity.json", "restore-status.json", "data/research.db")
            ):
                raise ValueError("untrusted restored path")
            marker = path / MARKER
            if marker.exists() and (
                marker.is_symlink()
                or marker.stat().st_size > 4096
                or json.loads(marker.read_text()).get("state") != "complete"
            ):
                raise ValueError("operation incomplete")
            identity = json.loads((path / "workspace-identity.json").read_text())
            status = json.loads((path / "restore-status.json").read_text())
            if identity != {"restore_id": identifier} or status != {"status": "complete"}:
                raise ValueError("identity mismatch")
            if not (path / "data/research.db").is_file():
                raise ValueError("database missing")
        except (OSError, ValueError) as exc:
            raise EngineError("RESTORE_INCOMPLETE", status=409) from exc
        return path
