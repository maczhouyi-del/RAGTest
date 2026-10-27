import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.storage.backup import Backups
from ragsystem.storage.backup_operations import BackupOperations
from ragsystem.storage.backup_service import BackupService
from ragsystem.storage.database import Database

ROOT = Path(__file__).resolve().parents[2]


def setup(tmp_path):
    root = tmp_path / "workspace"
    db = Database(root / "data/research.db")
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"%PDF-1.4\nbackup fault storage fixture\n%%EOF")
    PdfImporter(db, root).import_path_for_test(source, "import")
    # This storage-only synthetic PDF deliberately has no parseable metadata.
    for job in Jobs(db).list():
        if job["status"] == "queued":
            Jobs(db).cancel(job["id"])
    parent = tmp_path / "output"
    parent.mkdir()
    snapshot = Backups(db, root).create(parent)
    return root, db, parent, snapshot


@pytest.mark.parametrize("fault", ["backup_copy", "restore_copy", "db_init", "final_status"])
def test_partial_task_quarantined_original_unchanged_and_next_succeeds(
    tmp_path, monkeypatch, fault
):
    import ragsystem.storage.backup as module

    root, db, parent, snapshot = setup(tmp_path)
    originals = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "papers").glob("*.pdf")
    }
    service = BackupService(db, root)
    jobs, grants = Jobs(db), Directories()
    job = jobs.enqueue("backup", fault, {})
    original_copy = module.copy_new
    original_db = module.Database
    original_complete = jobs.complete
    with monkeypatch.context() as patch:
        if fault in {"backup_copy", "restore_copy"}:

            def bad_copy(source, target):
                Path(target).write_bytes(b"partial")
                raise OSError("injected disk exhausted")

            patch.setattr(module, "copy_new", bad_copy)
        elif fault == "db_init":
            patch.setattr(
                module,
                "Database",
                lambda *args: (_ for _ in ()).throw(OSError("injected database init")),
            )
        else:
            patch.setattr(
                service.jobs,
                "complete",
                lambda *args, **kwargs: (_ for _ in ()).throw(OSError("injected publication")),
            )
        source = None if fault == "backup_copy" else grants.issue(snapshot, "snapshot")
        service.run(
            job["id"],
            grants.issue(parent, "backup_parent" if source is None else "restore_parent"),
            source,
        )
    assert jobs.get(job["id"])["status"] == "failed"
    operation = next(row for row in service.operations.rows() if row["job_id"] == job["id"])
    assert operation["state"] == "quarantined"
    assert Path(operation["target"]).is_dir()
    assert not (parent / operation["original_name"]).exists()
    assert service.records() == []
    with pytest.raises(EngineError, match="NOT_FOUND"):
        service.restored_path(operation["id"])
    with pytest.raises(EngineError):
        Backups.inspect(Path(operation["target"]))
    assert originals == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "papers").glob("*.pdf")
    }
    assert Backups.inspect(snapshot)["document_count"] == 1
    assert db.integrity()["integrity_check"] == ["ok"]
    next_job = jobs.enqueue("backup", "successful-followup", {})
    service.run(
        next_job["id"], grants.issue(parent, "restore_parent"), grants.issue(snapshot, "snapshot")
    )
    assert jobs.get(next_job["id"])["status"] == "completed"
    record = service.records()[0]
    restored = service.restored_path(record["id"])
    assert restored != root and restored.is_dir()
    # Copied operation journals must never touch source-workspace outputs.
    BackupOperations(Database(restored / "data/research.db"), restored).reconcile()
    assert snapshot.exists() and root.exists()
    assert original_copy is module.copy_new and original_db is module.Database
    assert original_complete.__func__ is jobs.complete.__func__


@pytest.mark.parametrize("kind", ["backup", "restored"])
def test_real_process_kill_partial_output_reconciled_on_next_start(tmp_path, kind):
    root, db, parent, snapshot = setup(tmp_path)
    ready = tmp_path / "copy-started.json"
    script = """
import sys,time
from pathlib import Path
import ragsystem.storage.backup as module
from ragsystem.storage.backup_operations import BackupOperations
from ragsystem.storage.database import Database
root,parent,snapshot,ready=map(Path,sys.argv[1:5]);kind=sys.argv[5]
db=Database(root/'data/research.db');ops=BackupOperations(db,root)
value=ops.begin(kind,parent)
def pause(source,target):
    Path(target).write_bytes(b'partial')
    ready.write_text(value['id'])
    while True:time.sleep(.1)
module.copy_new=pause
if kind=='backup':module.Backups(db,root).create(parent,operation=(ops,value))
else:module.Backups.restore(snapshot,Path(value['target']),operation=(ops,value))
"""
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(root), str(parent), str(snapshot), str(ready), kind],
        env={**os.environ, "PYTHONPATH": str(ROOT / "engine")},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            assert child.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.02)
    finally:
        child.kill()
        child.wait(timeout=5)
    # Same method used by create_app startup, with a newly reopened journal.
    operations = BackupOperations(Database(db.path), root)
    with TestClient(
        create_app("a" * 64, root), base_url="http://127.0.0.1", headers={"X-RAG-Session": "a" * 64}
    ) as client:
        assert any(
            value["id"] == ready.read_text()
            for value in client.get("/v0/backups").json()["incomplete"]
        )
    row = next(value for value in operations.rows() if value["id"] == ready.read_text())
    assert row["state"] == "quarantined" and Path(row["target"]).is_dir()
    assert Backups.inspect(snapshot)["document_count"] == 1


def test_unverifiable_or_activated_output_left_untouched(tmp_path):
    root, db, parent, snapshot = setup(tmp_path)
    ops = BackupOperations(db, root)
    for issue in ["marker", "activated"]:
        row = ops.begin("restored", parent)
        target = ops.prepare(row)
        if issue == "marker":
            (target / ".ragsystem-operation.json").write_text('{"id":"other"}')
        else:
            (target / "data").mkdir()
            (target / "data/.engine.lock").write_text("held-or-historical-workspace")
        assert not ops.quarantine(row, "TEST_FAILURE")
        assert target.is_dir() and row["state"] == "manual_review"
    assert snapshot.is_dir()


def test_direct_restore_helper_quarantines_owned_copy_error(tmp_path, monkeypatch):
    import ragsystem.storage.backup as module

    root, db, parent, snapshot = setup(tmp_path)
    target = parent / "direct-restore"
    with monkeypatch.context() as patch:

        def fail_copy(*args):
            raise OSError("injected direct-helper I/O")

        patch.setattr(module, "copy_new", fail_copy)
        with pytest.raises(OSError):
            Backups.restore(snapshot, target)
    assert not target.exists()
    assert len(list(parent.glob("direct-restore.incomplete-*"))) == 1
    Backups.restore(snapshot, parent / "direct-retry")
    assert snapshot.exists() and root.exists()
