from pathlib import Path

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database
from ragsystem.storage.workspace_lock import WorkspaceLock
from ragsystem.workflows.workbench import Workbench

ROOT = Path(__file__).resolve().parents[2]


def test_exclusive_workspace_lock_and_restart_fences_predecessor_and_queued_jobs(tmp_path):
    lock = WorkspaceLock(tmp_path)
    with pytest.raises(EngineError, match="WORKSPACE_IN_USE"):
        WorkspaceLock(tmp_path)
    db = Database(tmp_path / "data/research.db")
    jobs = Jobs(db)
    active = jobs.enqueue("backup", "active", {})
    old = jobs.claim(active["id"], lease_seconds=1800)
    queued = jobs.enqueue("verify", "queued", {})
    assert jobs.recover_owned_workspace(lock) == 2
    assert jobs.get(active["id"])["status"] == jobs.get(queued["id"])["status"] == "retry_wait"
    with pytest.raises(EngineError, match="LEASE_LOST"):
        jobs.complete(active["id"], old["lease_token"], "stale")
    lock.close()
    reopened = WorkspaceLock(tmp_path)
    reopened.close()
    assert (tmp_path / "data/.engine.lock").exists()


def test_research_cancel_resume_reuses_committed_chunks_without_overwriting_review(
    tmp_path, monkeypatch
):
    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "import"
    )["doc_version_id"]
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    plan = work.create_plan("BERT", ["BERT"], [version], None, "extractive")
    jobs = Jobs(db)
    first = jobs.enqueue("research_extract", "first", {"plan_id": plan["id"]})
    heartbeat = work.jobs.heartbeat
    calls = []

    def cancel_after_commit(*args, **kwargs):
        calls.append(1)
        if len(calls) == 4:
            jobs.cancel(first["id"])
        return heartbeat(*args, **kwargs)

    monkeypatch.setattr(work.jobs, "heartbeat", cancel_after_commit)
    work.execute_plan(plan["id"], first["id"])
    partial = work.plans()[0]
    assert partial["status"] == "cancelled"
    item = partial["items"][0]
    assert 0 < item["processed_chunks"] < item["total_chunks"]
    previous_ids = [value["evidence_id"] for value in item["observations"]]
    if previous_ids:
        work.review(previous_ids[0], "confirmed", "复核保持")
    monkeypatch.setattr(work.jobs, "heartbeat", heartbeat)
    second = jobs.enqueue("research_extract", "second", {"plan_id": plan["id"]})
    work.execute_plan(plan["id"], second["id"])
    completed = work.plans()[0]
    assert completed["coverage"]["completed"] == 1
    assert completed["items"][0]["processed_chunks"] == 64
    assert [value["evidence_id"] for value in completed["items"][0]["observations"]][
        : len(previous_ids)
    ] == previous_ids
    if previous_ids:
        assert (
            next(record for record in completed["evidence"] if record["id"] == previous_ids[0])[
                "human_status"
            ]
            == "confirmed"
        )
    assert db.integrity()["foreign_key_check"] == []


def test_generator_cancelled_load_does_not_publish_config(tmp_path, monkeypatch):
    from ragsystem.ipc.directories import Directories
    from ragsystem.models.generation_service import GenerationService

    db = Database(tmp_path / "data/research.db")
    jobs = Jobs(db)
    row = jobs.enqueue("verify", "model", {})
    claimed = jobs.claim(row["id"])

    class CancelledLoad:
        fingerprint = {"engineering_fixture": True}

        def __init__(self, path, diagnostic_directory=None, cancel_check=None):
            jobs.cancel(row["id"])

        def close(self):
            self.closed = True

    monkeypatch.setattr("ragsystem.models.generation_service.LocalGenerator", CancelledLoad)
    service = GenerationService(db)
    with pytest.raises(EngineError, match="LEASE_LOST"):
        service.configure(Directories().issue(tmp_path, "generator"), claimed)
    assert not service.status()["configured"]
    with db.connection() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM app_settings WHERE key='generator'").fetchone()[0]
            == 0
        )


def test_research_failed_paper_does_not_hide_other_papers(tmp_path, monkeypatch):
    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    importer = PdfImporter(db, root)
    versions = [
        importer.import_path_for_test(ROOT / "tests/fixtures/public" / name, name)["doc_version_id"]
        for name in ("N19-1423.pdf", "2020.emnlp-main.550.pdf")
    ]
    for index, version in enumerate(versions):
        Parser(db, root).parse(version, "parse-" + str(index))
    work = Workbench(db, root, HybridSearch(db, root))
    plan = work.create_plan("BERT", ["BERT"], versions, None, "extractive")
    original = work.chunks_for

    def failed_paper(version):
        if version == versions[0]:
            raise EngineError("INJECTED_PAPER_FAILURE")
        return original(version)

    monkeypatch.setattr(work, "chunks_for", failed_paper)
    job = Jobs(db).enqueue("research_extract", "per-paper", {"plan_id": plan["id"]})
    work.execute_plan(plan["id"], job["id"])
    result = work.plans()[0]
    assert result["coverage"]["failed"] == 1 and result["coverage"]["completed"] == 1
    assert (
        next(item for item in result["items"] if item["doc_version_id"] == versions[0])[
            "error_code"
        ]
        == "INJECTED_PAPER_FAILURE"
    )


def test_model_worker_crash_isolated_and_diagnostics_retained(tmp_path, monkeypatch):
    import subprocess
    import sys

    from ragsystem.models.generator_worker import IsolatedGenerator

    real_popen = subprocess.Popen
    fixture = 'import sys,json,os;sys.stdin.readline();print(json.dumps({"ok":True,"fingerprint":{"fixture":"not-real-model"}}),flush=True);sys.stdin.readline();print("injected native worker crash",file=sys.stderr,flush=True);os._exit(13)'

    def launch(command, **kwargs):
        return real_popen([sys.executable, "-c", fixture], **kwargs)

    monkeypatch.setattr("ragsystem.models.generator_worker.subprocess.Popen", launch)
    generator = IsolatedGenerator(tmp_path / "not-a-real-model", tmp_path / "diagnostics")
    with pytest.raises(EngineError, match="MODEL_WORKER_FAILED"):
        generator.generate("answer", {"chunks": []})
    # The supervising test process remains alive, and a new worker is possible.
    with pytest.raises(EngineError, match="MODEL_WORKER_FAILED"):
        generator.generate("answer", {"chunks": []})
    generator.close()
    import time

    deadline = time.monotonic() + 3
    while not all(
        "injected native worker crash" in p.read_text()
        for p in (tmp_path / "diagnostics").glob("*.log")
    ):
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert len(list((tmp_path / "diagnostics").glob("*.log"))) == 2


def test_generator_cancellation_during_loading_terminates_exact_worker(tmp_path, monkeypatch):
    import subprocess
    import sys

    from ragsystem.models.generator_worker import IsolatedGenerator

    created = []
    original = subprocess.Popen

    def launch(command, **kwargs):
        process = original(
            [sys.executable, "-c", "import sys,time;sys.stdin.readline();time.sleep(10)"], **kwargs
        )
        created.append(process)
        return process

    monkeypatch.setattr("ragsystem.models.generator_worker.subprocess.Popen", launch)
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise EngineError("LEASE_LOST")

    with pytest.raises(EngineError, match="LEASE_LOST"):
        IsolatedGenerator(
            tmp_path / "engineering-only-placeholder", tmp_path / "diagnostics", cancel_check=cancel
        )
    assert len(created) == 1 and created[0].poll() is not None
