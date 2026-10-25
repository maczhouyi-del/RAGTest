import hashlib
import json
import re
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from ragsystem import __version__
from ragsystem.domain.errors import EngineError
from ragsystem.ipc.directories import directory_identity
from ragsystem.storage.database import SCHEMA_VERSION, Database, utc_now


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def copy_new(source, target):
    with Path(source).open("rb") as incoming, Path(target).open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)


class Backups:
    def __init__(self, db: Database, root: Path):
        self.db, self.root = db, Path(root)

    def create(self, destination: Path, *, progress=lambda current, total: None):
        """Trusted operator or purpose-bound broker directory grant only."""
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        directory_identity(destination)
        snapshot = destination / ("ragsystem-backup-" + str(uuid4()))
        (snapshot / "data").mkdir(parents=True)
        (snapshot / "papers").mkdir()
        target_db = snapshot / "data/research.db"
        progress(0, 1)
        with self.db.connection() as source, sqlite3.connect(target_db) as backup:
            source.backup(
                backup, pages=256, progress=lambda status, remaining, total: progress(0, 1)
            )
            backup.execute("PRAGMA journal_mode=DELETE")
            backup.execute("PRAGMA trusted_schema=OFF")
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise EngineError("BACKUP_DATABASE_INVALID")
            hashes = [row[0] for row in backup.execute("SELECT sha256 FROM file_assets")]
            spaces = [
                row[0] for row in backup.execute("SELECT fingerprint_json FROM embedding_spaces")
            ]
            vector_count = backup.execute("SELECT COUNT(*) FROM embedding_records").fetchone()[0]
        records = [{"path": "data/research.db", "sha256": sha256(target_db)}]
        for index, digest in enumerate(hashes):
            progress(index, len(hashes))
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise EngineError("BACKUP_DATABASE_INVALID")
            relative = "papers/" + digest + ".pdf"
            source_file, target_file = self.root / relative, snapshot / relative
            if source_file.is_symlink():
                raise EngineError("OBJECT_CORRUPT")
            copy_new(source_file, target_file)
            if sha256(target_file) != digest:
                raise EngineError("BACKUP_HASH_MISMATCH")
            records.append({"path": relative, "sha256": digest})
        progress(len(hashes), len(hashes))
        manifest = {
            "manifest_version": "0.1.0",
            "application_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "created_at": utc_now(),
            "status": "complete",
            "embedding_state": "PERSISTED_IN_SQLITE" if vector_count else "NOT_CONFIGURED",
            "embedding_spaces": [json.loads(value) for value in spaces],
            "embedding_count": vector_count,
            "derived_vector_indexes_included": False,
            "files": records,
        }
        with (snapshot / "manifest.json").open("x") as stream:
            json.dump(manifest, stream, indent=2)
        return snapshot

    @staticmethod
    def inspect(snapshot: Path, *, progress=lambda current, total: None):
        snapshot = Path(snapshot)
        directory_identity(snapshot)
        manifest_path = snapshot / "manifest.json"
        try:
            if manifest_path.is_symlink() or manifest_path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError("invalid manifest")
            manifest = json.loads(manifest_path.read_text())
            records = manifest["files"]
            if (
                manifest["manifest_version"] != "0.1.0"
                or manifest["status"] != "complete"
                or type(manifest["schema_version"]) is not int
                or not 1 <= manifest["schema_version"] <= SCHEMA_VERSION
                or not isinstance(records, list)
                or not 1 <= len(records) <= 10000
            ):
                raise ValueError("invalid manifest")
            seen, total_bytes = set(), 0
            for index, record in enumerate(records):
                progress(index, len(records))
                relative, expected = record["path"], record["sha256"]
                if (
                    not isinstance(relative, str)
                    or relative in seen
                    or not isinstance(expected, str)
                    or not re.fullmatch(r"[a-f0-9]{64}", expected)
                    or (
                        relative != "data/research.db"
                        and not re.fullmatch(r"papers/[a-f0-9]{64}\.pdf", relative)
                    )
                ):
                    raise ValueError("invalid path/hash")
                path = snapshot / relative
                directory_identity(path.parent)
                if path.is_symlink() or not path.is_file():
                    raise ValueError("invalid file")
                if relative.startswith("papers/") and (
                    Path(relative).stem != expected or path.stat().st_size > 64 * 1024 * 1024
                ):
                    raise ValueError("file identity/size invalid")
                total_bytes += path.stat().st_size
                if total_bytes > 8 * 1024**3 or (
                    relative == "data/research.db" and path.stat().st_size > 512 * 1024**2
                ):
                    raise ValueError("backup resource limit")
                seen.add(relative)
                if sha256(path) != expected:
                    raise EngineError("BACKUP_HASH_MISMATCH")
            if "data/research.db" not in seen:
                raise ValueError("database missing")
            uri = (snapshot / "data/research.db").resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                conn.execute("PRAGMA trusted_schema=OFF")
                if (
                    conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                    or conn.execute("PRAGMA foreign_key_check").fetchall()
                    or conn.execute("PRAGMA user_version").fetchone()[0]
                    != manifest["schema_version"]
                ):
                    raise EngineError("BACKUP_DATABASE_INVALID")
                required = {
                    "papers/" + row[0] + ".pdf"
                    for row in conn.execute("SELECT sha256 FROM file_assets")
                }
                if required != seen - {"data/research.db"}:
                    raise ValueError("manifest/database mismatch")
                documents = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                vectors = conn.execute("SELECT COUNT(*) FROM embedding_records").fetchone()[0]
            progress(len(records), len(records))
            return {
                "manifest": manifest,
                "document_count": documents,
                "embedding_count": vectors,
                "manifest_sha256": sha256(manifest_path),
            }
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            raise EngineError("BACKUP_MANIFEST_INVALID") from exc

    @staticmethod
    def restore(snapshot: Path, target: Path, *, progress=lambda current, total: None):
        snapshot, target = Path(snapshot), Path(target)
        if target.exists():
            raise EngineError("RESTORE_TARGET_EXISTS", status=409)
        manifest = Backups.inspect(snapshot, progress=progress)["manifest"]
        directory_identity(target.parent)
        target.mkdir(exist_ok=False)
        (target / "restore-status.json").write_text('{"status":"incomplete"}\n')
        for index, record in enumerate(manifest["files"]):
            progress(index, len(manifest["files"]))
            path = target / record["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            copy_new(snapshot / record["path"], path)
            if sha256(path) != record["sha256"]:
                raise EngineError("BACKUP_HASH_MISMATCH")
        restored = Database(target / "data/research.db")
        # Leases in a restored snapshot belong to the old workspace/process.
        # Fence them immediately; never show copied running work as live.
        with restored.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status IN ('queued','running','retry_wait','cancelling')"
            ).fetchall()
            for row in rows:
                state = (
                    "failed"
                    if row["type"] == "backup" or row["attempt_count"] >= row["max_attempts"]
                    else "retry_wait"
                )
                conn.execute(
                    "UPDATE jobs SET status=?,lease_token=NULL,lease_until=NULL,error_code='RESTORED_JOB_REQUIRES_REVIEW',updated_at=? WHERE id=?",
                    (state, utc_now(), row["id"]),
                )
                conn.execute(
                    "UPDATE job_attempts SET finished_at=?,outcome='restored_snapshot' WHERE job_id=? AND finished_at IS NULL",
                    (utc_now(), row["id"]),
                )
                conn.execute(
                    "INSERT INTO events(job_id,kind,details_json,created_at) VALUES(?,'restored_snapshot','{}',?)",
                    (row["id"], utc_now()),
                )
            conn.execute(
                "UPDATE parse_runs SET status='failed',error_code='RESTORED_PARSE_INTERRUPTED',finished_at=? WHERE status='running'",
                (utc_now(),),
            )
            conn.execute(
                "UPDATE parse_attempts SET status='failed',error_code='RESTORED_PARSE_INTERRUPTED',finished_at=? WHERE status='running'",
                (utc_now(),),
            )
        progress(len(manifest["files"]), len(manifest["files"]))
        (target / "restore-status.json").write_text('{"status":"complete"}\n')
        return target
