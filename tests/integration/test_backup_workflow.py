import secrets
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.library.repository import Library
from ragsystem.storage.database import Database

ROOT = Path(__file__).resolve().parents[2]


def test_directory_grants_bind_purpose_identity_and_expiry(tmp_path):
    directory = tmp_path / "输出 空格"
    directory.mkdir()
    grants = Directories()
    grant = grants.issue(directory, "backup_parent")
    with pytest.raises(EngineError, match="GRANT_INVALID"):
        grants.take(grant.id, "restore_parent")
    grant = grants.issue(directory, "backup_parent")
    grant.expires = time.monotonic() - 1
    with pytest.raises(EngineError, match="GRANT_EXPIRED"):
        grants.take(grant.id, "backup_parent")
    grant = grants.issue(directory, "backup_parent")
    directory.rename(tmp_path / "原授权目录")
    directory.mkdir()
    with pytest.raises(EngineError, match="DIRECTORY_CHANGED"):
        grants.take(grant.id, "backup_parent")


def test_backup_restore_jobs_and_fresh_workspace_do_not_overwrite_original(tmp_path):
    root = tmp_path / "工作区"
    db = Database(root / "data/research.db")
    PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "import"
    )
    library = Library(db)
    project = library.create_project("备份项目")
    library.set_membership(project["id"], library.list_documents()[0]["document_id"], True)
    parent = tmp_path / "备份 恢复位置"
    parent.mkdir()
    token = secrets.token_hex(32)
    headers = {"X-RAG-Session": token}
    with TestClient(create_app(token, root), base_url="http://127.0.0.1") as client:

        def grant(path, purpose):
            return client.post(
                "/v0/internal/directory-grants",
                headers=headers,
                json={"path": str(path), "purpose": purpose},
            ).json()["directory_grant_id"]

        body = {"parent_grant_id": grant(parent, "backup_parent"), "idempotency_key": "backup"}
        first = client.post("/v0/backups", headers=headers, json=body)
        assert first.status_code == 202
        assert (
            client.post("/v0/backups", headers=headers, json=body).json()["job_id"]
            == first.json()["job_id"]
        )
        records = client.get("/v0/backups", headers=headers).json()["records"]
        assert records[0]["kind"] == "backup" and "local_path" not in records[0]
        snapshot = next(parent.glob("ragsystem-backup-*"))
        result = client.post(
            "/v0/backups",
            headers=headers,
            json={
                "parent_grant_id": grant(parent, "restore_parent"),
                "source_grant_id": grant(snapshot, "snapshot"),
                "idempotency_key": "restore",
            },
        )
        assert result.status_code == 202
        restored = next(
            row
            for row in client.get("/v0/backups", headers=headers).json()["records"]
            if row["kind"] == "restored"
        )
        path = Path(
            client.get(
                "/v0/internal/restored-workspaces/" + restored["id"], headers=headers
            ).json()["data_root"]
        )
        assert path != root and path.parent == parent
        assert (
            Library(Database(path / "data/research.db")).list_documents()
            == library.list_documents()
        )
        assert (
            Library(Database(path / "data/research.db")).list_projects() == library.list_projects()
        )
        with Database(path / "data/research.db").connection() as conn:
            assert (
                conn.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0] == 0
            )
        assert root.exists() and db.integrity()["integrity_check"] == ["ok"]


def test_cancelled_parse_retry_preserves_attempts_and_completed_cannot_repeat(tmp_path):
    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    imported = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "one"
    )
    from ragsystem.parsing.pipeline import Parser

    jobs = Jobs(db)
    row = Parser(db, root).parse(imported["doc_version_id"], "parse", queue_only=True)
    jobs.cancel(row["id"])
    token = secrets.token_hex(32)
    with TestClient(create_app(token, root), base_url="http://127.0.0.1") as client:
        headers = {"X-RAG-Session": token}
        assert client.post("/v0/jobs/" + row["id"] + "/retry", headers=headers).status_code == 202
        assert jobs.get(row["id"])["status"] == "completed"
        assert jobs.get(row["id"])["attempt_count"] == 1
        assert client.post("/v0/jobs/" + row["id"] + "/retry", headers=headers).status_code == 409


def test_manual_retry_does_not_reset_attempt_limit(tmp_path):
    jobs = Jobs(Database(tmp_path / "research.db"))
    row = jobs.enqueue("backup", "limit", {}, max_attempts=1)
    claimed = jobs.claim(row["id"])
    jobs.fail(row["id"], claimed["lease_token"], "TEST_FAILURE")
    with pytest.raises(EngineError, match="ATTEMPT_LIMIT"):
        jobs.retry(row["id"])
    assert jobs.get(row["id"])["attempt_count"] == 1
