import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database, utc_now
from ragsystem.workflows.preparation import Preparation
from ragsystem.workflows.workbench import Workbench


def versions(db, count):
    ids = [str(uuid4()) for _ in range(count)]
    with db.transaction() as conn:
        for n, version in enumerate(ids):
            digest = hashlib.sha256(str(n).encode()).hexdigest()
            doc = str(uuid4())
            conn.execute("INSERT INTO file_assets VALUES(?,?,?,?)", (digest, 10, "papers/"+digest+".pdf", utc_now()))
            conn.execute("INSERT INTO documents VALUES(?,?,?)", (doc, "synthetic storage fixture", utc_now()))
            conn.execute("INSERT INTO document_versions(id,document_id,file_sha256,visibility,created_at) VALUES(?,?,?,'visible',?)", (version, doc, digest, utc_now()))
    return ids


@pytest.mark.parametrize("count", [1, 418, 419, 1000])
def test_prepare_freezes_large_scope_with_bounded_payload(tmp_path, monkeypatch, count):
    db = Database(tmp_path / "data/research.db")
    scope = versions(db, count)
    received = []

    def run(self, identifier, version_ids):
        job = self.jobs.claim(identifier)
        if job:
            received.append(version_ids)
            self.jobs.complete(identifier, job["lease_token"], "fixture:admission-only")

    monkeypatch.setattr(Preparation, "run", run)
    with TestClient(create_app("a"*64, tmp_path), base_url="http://127.0.0.1", headers={"X-RAG-Session":"a"*64}) as client:
        response = client.post("/v0/mvp/prepare", json={"version_ids":scope,"idempotency_key":"scope"})
        assert response.status_code == 202, response.text
        job = Jobs(db).get(response.json()["job_id"])
        assert len(job["payload_json"].encode()) < 1024
        assert received == [sorted(scope)]
        assert client.post("/v0/mvp/prepare", json={"version_ids":list(reversed(scope)),"idempotency_key":"scope"}).json()["job_id"] == job["id"]
        if count > 1:
            assert client.post("/v0/mvp/prepare", json={"version_ids":scope[:-1],"idempotency_key":"scope"}).status_code == 409
    # Reopened DB can recover the exact frozen IDs; admission is not a throughput test.
    assert Preparation(Database(db.path), tmp_path, None).versions(job["id"]) == sorted(scope)


def test_cancel_before_answer_claim_terminates_business_record(tmp_path, monkeypatch):
    db = Database(tmp_path / "data/research.db")
    work = Workbench(db, tmp_path, HybridSearch(db, tmp_path))
    run = work.create_answer("你是什么模型", [], None, "extractive", "keyword")
    entered, proceed = threading.Event(), threading.Event()
    original = work.jobs.claim

    def claim(*args, **kwargs):
        entered.set()
        assert proceed.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(work.jobs, "claim", claim)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(work.run_answer, run["id"])
        try:
            assert entered.wait(5)
            Jobs(db).cancel(run["job_id"])
        finally:
            proceed.set()
        pending.result(timeout=5)
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM answer_runs WHERE id=?", (run["id"],)).fetchone()
        assert row["status"] == "cancelled" and row["error_code"] == "JOB_CANCELLED"
        assert conn.execute("SELECT count(*) FROM claim_records").fetchone()[0] == 0
    assert Jobs(db).get(run["job_id"])["status"] == "cancelled"
    assert work.create_answer("你是什么模型", [], None, "extractive", "keyword")["id"] != run["id"]


def test_restored_workspace_gate_protects_cancelled_but_live_executor(tmp_path, monkeypatch):
    entered, finish = threading.Event(), threading.Event()

    def build(self, identifier, grant, backend, **kwargs):
        self.jobs.claim(identifier)
        entered.set()
        assert finish.wait(5)

    monkeypatch.setattr(HybridSearch, "build", build)
    with TestClient(create_app("a"*64, tmp_path), base_url="http://127.0.0.1", headers={"X-RAG-Session":"a"*64}) as client, ThreadPoolExecutor(max_workers=1) as pool:
        grant = client.post("/v0/internal/directory-grants",json={"path":str(tmp_path),"purpose":"embedding"}).json()["directory_grant_id"]
        pending = pool.submit(client.post,"/v0/index",json={"model_grant_id":grant,"backend":"sqlite-vec","idempotency_key":"live"})
        try:
            assert entered.wait(5)
            job = Jobs(Database(tmp_path/"data/research.db")).find_key("embed_batch","live")
            assert client.post("/v0/jobs/"+job["id"]+"/cancel").status_code == 202
            assert client.get("/v0/internal/restored-workspaces/unknown").status_code == 429
        finally:
            finish.set()
            pending.result(timeout=5)
        assert client.get("/v0/internal/restored-workspaces/unknown").status_code == 404


@pytest.mark.parametrize("previous_status", ["queued", "running"])
def test_restart_all_job_intents_can_be_cancelled_before_restore_activation(tmp_path, previous_status):
    from ragsystem.ipc.directories import Directories
    from ragsystem.storage.backup import Backups
    from ragsystem.storage.backup_service import BackupService
    from ragsystem.storage.workspace_lock import WorkspaceLock

    root = tmp_path / "source"
    db = Database(root / "data/research.db")
    parent = tmp_path / "copies"
    parent.mkdir()
    snapshot = Backups(db, root).create(parent)
    service, grants, jobs = BackupService(db, root), Directories(), Jobs(db)
    restored = jobs.enqueue("backup", "restore", {})
    service.run(restored["id"], grants.issue(parent, "restore_parent"), grants.issue(snapshot, "snapshot"))
    record = service.records()[0]
    cases = [(kind, {}) for kind in sorted(Jobs.TYPES)] + [("verify", {"action": action}) for action in ("mvp_prepare", "answer", "configure_ocr")]
    intents = []
    for i, (kind, payload) in enumerate(cases):
        row = jobs.enqueue(kind, "restart-"+str(i), payload)
        old = jobs.claim(row["id"]) if previous_status == "running" else None
        intents.append((row, old))
    lock = WorkspaceLock(root)
    try:
        jobs.recover_owned_workspace(lock)
    finally:
        lock.close()
    with TestClient(create_app("a"*64, root), base_url="http://127.0.0.1", headers={"X-RAG-Session":"a"*64}) as client:
        assert client.get("/v0/internal/restored-workspaces/"+record["id"]).status_code == 409
        for row, old in intents:
            assert jobs.get(row["id"])["status"] == "retry_wait"
            assert client.post("/v0/jobs/"+row["id"]+"/cancel").json()["status"] == "cancelled"
            if old:
                from ragsystem.domain.errors import EngineError
                with pytest.raises(EngineError, match="LEASE_LOST"):
                    jobs.complete(row["id"], old["lease_token"], "invalid:old-executor")
        activated = client.get("/v0/internal/restored-workspaces/"+record["id"])
        assert activated.status_code == 200
        assert service.restored_path(record["id"]).is_dir()


def test_prepare_snapshot_atomicity_legacy_and_tamper_detection(tmp_path, monkeypatch):
    from ragsystem.domain.errors import EngineError

    db = Database(tmp_path / "data/research.db")
    ids = versions(db, 2)
    preparation = Preparation(db, tmp_path, None)
    original = Jobs.enqueue
    def fail(*args, **kwargs):
        raise OSError("injected enqueue failure")
    with monkeypatch.context() as patch:
        patch.setattr(Jobs, "enqueue", fail)
        with pytest.raises(OSError):
            preparation.enqueue(ids, "rollback")
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) FROM scope_snapshots").fetchone()[0] == 0
    old = original(Jobs(db), "verify", "legacy", {"action":"mvp_prepare","versions":sorted(ids)})
    assert preparation.versions(old["id"]) == sorted(ids)
    new = preparation.enqueue(ids, "new")
    with db.transaction() as conn:
        conn.execute("UPDATE scope_snapshots SET versions_json='[]'")
    with pytest.raises(EngineError, match="SCOPE_IDENTITY_CHANGED"):
        preparation.versions(new["id"])
