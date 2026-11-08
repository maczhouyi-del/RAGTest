"""Isolated storage/IPC fault regressions; no real workspace or remote model."""
import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.storage.database import Database


def published_intent(root, db, key, content):
    digest = hashlib.sha256(content).hexdigest()
    (root / "papers").mkdir(exist_ok=True)
    (root / "papers" / (digest + ".pdf")).write_bytes(content)
    job = Jobs(db).enqueue("import", key, {"sha256": digest, "size_bytes": len(content)})
    return job, root / "papers" / (digest + ".pdf")


@pytest.mark.parametrize("replacement", [b"broken header", b"%PDF-1.4\nB valid storage bytes\n"])
@pytest.mark.parametrize("route", ["startup", "resume"])
def test_recovery_binds_expected_object_and_isolates_bad_pdf(tmp_path, replacement, route):
    root = tmp_path / "恢复 中文"
    db = Database(root / "data/research.db")
    importer = PdfImporter(db, root)
    bad, path = published_intent(root, db, "bad", b"%PDF-1.4\nA expected bytes\n")
    good, _ = published_intent(root, db, "good", b"%PDF-1.4\nGood bytes\n")
    path.write_bytes(replacement)
    if route == "startup":
        with TestClient(create_app("a" * 64, root), base_url="http://127.0.0.1",
                        headers={"X-RAG-Session": "a" * 64}) as client:
            assert client.get("/v0/health").status_code == 200
    else:
        with pytest.raises(EngineError, match="OBJECT_CORRUPT"):
            importer.resume(bad["id"])
        assert importer.recover_published_imports() == 1
    assert Jobs(db).get(bad["id"])["status"] == "failed"
    assert Jobs(db).get(bad["id"])["error_code"] == "OBJECT_CORRUPT"
    assert Jobs(db).get(good["id"])["status"] == "completed"
    assert len(importer.list_documents()) == 1
    assert path.read_bytes() == replacement
    assert not (root / "papers" / (hashlib.sha256(replacement).hexdigest() + ".pdf")).exists()


def test_recovery_does_not_swallow_database_failure(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    db = Database(root / "data/research.db")
    importer = PdfImporter(db, root)
    published_intent(root, db, "good", b"%PDF-1.4\nstorage only\n")

    def fail(*args, **kwargs):
        raise sqlite3.DatabaseError("injected database corruption")

    monkeypatch.setattr(importer.jobs, "claim", fail)
    with pytest.raises(sqlite3.DatabaseError):
        importer.recover_published_imports()


def test_claimed_import_rechecks_original_intent(tmp_path):
    from ragsystem.ipc.grants import Grants

    root = tmp_path / "workspace"
    db = Database(root / "data/research.db")
    importer = PdfImporter(db, root)
    job, _ = published_intent(root, db, "A", b"%PDF-1.4\nA\n")
    source = tmp_path / "B.pdf"
    source.write_bytes(b"%PDF-1.4\nB\n")
    grants = Grants()
    try:
        grant = grants.issue(source)
        with pytest.raises(EngineError, match="OBJECT_CORRUPT"):
            importer.run(Jobs(db).claim(job["id"]), grant)
        assert Jobs(db).get(job["id"])["status"] == "failed"
        assert importer.list_documents() == []
        assert list((root / "staging").iterdir()) == []
    finally:
        grants.close()


def test_real_sidecar_starts_with_bad_and_good_recovery_intents(tmp_path):
    from test_sidecar_lifecycle import start_sidecar, stop_sidecar

    root = tmp_path / "中文 空格"
    db = Database(root / "data/research.db")
    bad, path = published_intent(root, db, "bad", b"%PDF-1.4\nA\n")
    good, _ = published_intent(root, db, "good", b"%PDF-1.4\nGood\n")
    path.write_bytes(b"corrupted object")
    process, client, token = start_sidecar(tmp_path)
    try:
        headers = {"X-RAG-Session": token}
        assert client.get("/v0/jobs/" + bad["id"], headers=headers).json()["status"] == "failed"
        assert client.get("/v0/jobs/" + good["id"], headers=headers).json()["status"] == "completed"
        assert len(client.get("/v0/documents", headers=headers).json()["documents"]) == 1
        assert path.read_bytes() == b"corrupted object"
    finally:
        client.close()
        stop_sidecar(process)


@pytest.mark.parametrize("endpoint,purpose", [("docling", "docling"), ("ocr", "ocr"), ("generator", "generator")])
@pytest.mark.parametrize("fault", ["claim", "configure", "fail"])
def test_configuration_failures_never_leak_heavy_slot(tmp_path, monkeypatch, endpoint, purpose, fault):
    from ragsystem.models.generation_service import GenerationService
    from ragsystem.parsing.docling import DoclingService
    from ragsystem.parsing.ocr import OcrService

    classes = {"docling": DoclingService, "ocr": OcrService, "generator": GenerationService}
    root = tmp_path / "workspace"
    db = Database(root / "data/research.db")
    original_claim, original_fail = Jobs.claim, Jobs.fail

    def claim(self, job_id, **kwargs):
        if fault == "claim" and self.get(job_id)["idempotency_key"] == "fault":
            raise sqlite3.OperationalError("injected claim I/O")
        return original_claim(self, job_id, **kwargs)

    def fail(self, job_id, token, code):
        if fault == "fail" and self.get(job_id)["idempotency_key"] == "fault":
            raise sqlite3.OperationalError("injected failure write I/O")
        return original_fail(self, job_id, token, code)

    def configure(self, grant, job):
        if job["idempotency_key"] == "fault":
            raise EngineError("INJECTED_CONFIGURATION_ERROR")
        Jobs(db).complete(job["id"], job["lease_token"], "fixture:configured")

    monkeypatch.setattr(Jobs, "claim", claim)
    monkeypatch.setattr(Jobs, "fail", fail)
    monkeypatch.setattr(classes[endpoint], "configure", configure)
    with TestClient(create_app("a" * 64, root), base_url="http://127.0.0.1",
                    headers={"X-RAG-Session": "a" * 64}, raise_server_exceptions=False) as client:
        def submit(key):
            grant = client.post("/v0/internal/directory-grants", json={"path": str(tmp_path), "purpose": purpose}).json()
            return client.post("/v0/" + endpoint, json={"model_grant_id": grant["directory_grant_id"], "idempotency_key": key})
        assert submit("fault").status_code == 202
        row = Jobs(db).find_key("verify", "fault")
        assert submit("after-fault").status_code == 202
        assert Jobs(db).find_key("verify", "after-fault")["status"] == "completed"
    if fault == "claim":
        assert Jobs(db).get(row["id"])["status"] == "failed"
    elif fault == "fail":
        Jobs(db).recover_expired(now=row["lease_until"] + 1)
        assert Jobs(db).get(row["id"])["status"] == "retry_wait"
    else:
        assert row["status"] == "failed" and row["error_code"] == "INJECTED_CONFIGURATION_ERROR"
