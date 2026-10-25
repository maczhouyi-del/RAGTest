import hashlib
from pathlib import Path

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.jobs.repository import Jobs
from ragsystem.library.lifecycle import Lifecycle
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.database import Database
from ragsystem.workflows.history import History
from ragsystem.workflows.workbench import Workbench

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "历史 生命周期"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "bert"
    )["doc_version_id"]
    Parser(db, root).parse(version, "parse")
    return root, db, version


def test_history_stable_tie_cursor_complete_older_detail_and_project_filter(store):
    root, db, version = store
    work = Workbench(db, root, HybridSearch(db, root))
    identifiers = []
    for index in range(36):
        identifiers.append(
            work.create_answer(f"BERT {index}", [version], None, "extractive", "keyword")["id"]
        )
    # Exercise tie-breaking independent of timestamps or SQLite row insertion order.
    with db.transaction() as conn:
        conn.execute("UPDATE answer_runs SET created_at='2026-10-24T00:00:00+00:00'")
    history = History(work)
    first = history.index("answers", limit=17)
    assert first["total"] == 36 and first["next_cursor"]
    newer = work.create_answer("new insertion", [version], None, "extractive", "keyword")
    second = history.index("answers", cursor=first["next_cursor"], limit=17)
    last = history.index("answers", cursor=second["next_cursor"], limit=17)
    ids = [row["id"] for page in [first, second, last] for row in page["items"]]
    assert len(ids) == len(set(ids)) == 36 and set(ids) == set(identifiers)
    assert newer["id"] not in ids and last["next_cursor"] is None
    assert history.answer(ids[-1], None)["id"] == ids[-1]
    project = Library(db).create_project("隔离")
    assert history.index("answers", project["id"])["total"] == 0
    with pytest.raises(EngineError, match="NOT_FOUND"):
        history.answer(ids[-1], project["id"])
    for cursor in ["!", "abc", "x" * 513]:
        with pytest.raises(EngineError, match="INVALID_CURSOR"):
            history.index("answers", cursor=cursor)
    with pytest.raises(EngineError, match="INVALID_REQUEST"):
        history.index("answers", limit=100)


def test_research_lazy_paper_observation_pages_and_report_body(store):
    root, db, version = store
    other = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/2020.emnlp-main.550.pdf", "dpr"
    )["doc_version_id"]
    work = Workbench(db, root, HybridSearch(db, root))
    plan = work.create_plan("逐篇", ["BERT"], [version, other], None, "extractive")
    job = Jobs(db).enqueue("research_extract", "run", {"plan_id": plan["id"]})
    work.execute_plan(plan["id"], job["id"])
    history = History(work)
    page = history.research(plan["id"], None, limit=1)
    assert page["scope_count"] == 2 and len(page["items"]) == len(page["evidence"]) == 1
    item = page["items"][0]
    assert item["observation_count"] > 1 and item["observation_next_offset"] == 1
    next_page = history.research(plan["id"], None, observation_offset=1, limit=1)
    assert next_page["evidence"][0]["id"] != page["evidence"][0]["id"]
    assert page["coverage"] == next_page["coverage"]
    assert history.research(plan["id"], None, paper_offset=1)["items"][0]["status"] == "needs_parse"
    report = work.report(plan["id"])
    references = history.research(plan["id"], None)["reports"]
    assert references[0]["id"] == report["id"] and "body" not in references[0]
    assert "Research" in work.report_content(report["id"])["body"]
    with pytest.raises(EngineError, match="INVALID_PAGE"):
        history.research(plan["id"], None, paper_offset=2)
    project = Library(db).create_project("other")
    with pytest.raises(EngineError, match="NOT_FOUND"):
        history.research(plan["id"], project["id"])


def test_retraction_fences_new_sources_and_marks_historical_reports_without_losing_original(store):
    root, db, version = store
    work = Workbench(db, root, HybridSearch(db, root))
    answer = work.create_answer("BERT", [version], None, "extractive", "keyword")
    work.run_answer(answer["id"])
    plan = work.create_plan("逐篇", ["BERT"], [version], None, "extractive")
    job = Jobs(db).enqueue("research_extract", "run", {"plan_id": plan["id"]})
    work.execute_plan(plan["id"], job["id"])
    report = work.report(plan["id"])
    body = work.report_content(report["id"])["body"]
    document = Library(db).list_documents()[0]
    original = root / "papers" / (document["file_sha256"] + ".pdf")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    lifecycle = Lifecycle(db)
    record = lifecycle.update(
        document["document_id"], 0, "retracted", "本地测试标记，未核实出版方状态"
    )
    assert record["origin"] == "manual_unverified" and record["revision"] == 1
    assert Library(db).list_documents() == []
    assert Library(db).file_record(version, root)["file_sha256"] == digest
    with pytest.raises(EngineError, match="SCOPE_NOT_AVAILABLE"):
        Sources(db, root).search("BERT", [version], 10)
    with pytest.raises(EngineError, match="SCOPE_NOT_AVAILABLE"):
        work.create_answer("BERT", [version], None, "extractive", "keyword")
    historical = work.answers()[0]
    assert all(e["current_source_status"] == "retracted" for e in historical["evidence"])
    revised = work.report_content(report["id"])
    assert revised["body"] == body and revised["source_warnings"][0]["state"] == "retracted"
    assert "来源状态提示" in revised["export_body"]
    assert History(work).research(plan["id"], None)["source_warnings"]
    with pytest.raises(EngineError, match="LIFECYCLE_CONFLICT"):
        lifecycle.update(document["document_id"], 0, "active", "stale")
    restored = lifecycle.update(document["document_id"], 1, "active", "恢复测试")
    assert len(restored["history"]) == 2
    assert Sources(db, root).search("BERT", [version], 1)
    assert work.report_content(report["id"])["body"] == body
    assert work.report_content(report["id"])["source_warnings"] == []
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    # Reimporting a flagged file cannot silently reactivate it.
    lifecycle.update(document["document_id"], 2, "archived", "停用")
    PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "duplicate"
    )
    assert Library(db).list_documents() == [] and len(lifecycle.records()[0]["history"]) == 3


def test_lifecycle_change_during_model_or_parse_work_cannot_publish(store, monkeypatch):
    root, db, version = store
    work = Workbench(db, root, HybridSearch(db, root))
    document = Library(db).list_documents()[0]

    class InactiveDuringInference:
        fingerprint = {"fixture": "engineering-only"}

        def generate(self, task, data):
            if task == "support":
                Lifecycle(db).update(document["document_id"], 0, "archived", "concurrent change")
                return {"status": "supported", "reason": "fixture"}
            chunk = data["chunks"][0]
            return {
                "claims": [
                    {
                        "text": "fixture",
                        "evidence": [{"chunk_id": chunk["chunk_id"], "quote": chunk["text"][:20]}],
                    }
                ]
            }

    work.generation.generator = InactiveDuringInference()
    run = work.create_answer("BERT", [version], None, "generative", "keyword")
    work.run_answer(run["id"])
    assert work.answers()[0]["error_code"] == "SCOPE_NOT_AVAILABLE"
    assert work.answers()[0]["evidence"] == []
    Lifecycle(db).update(document["document_id"], 1, "active", "restore")
    import ragsystem.parsing.pipeline as pipeline

    original = pipeline.run_worker

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        Lifecycle(db).update(document["document_id"], 2, "archived", "during parse")
        return result

    monkeypatch.setattr(pipeline, "run_worker", changed)
    with pytest.raises(EngineError, match="SCOPE_NOT_AVAILABLE"):
        Parser(db, root).parse(version, "late parse")
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chunks WHERE visible=1").fetchone()[0] == 64


def test_inactive_merge_undo_is_fenced_and_prior_hidden_versions_stay_hidden(store):
    from ragsystem.library.identity import Identity

    root, db, version = store
    other = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/2020.emnlp-main.550.pdf", "dpr"
    )["doc_version_id"]
    docs = {row["doc_version_id"]: row for row in Library(db).list_documents()}
    identity = Identity(db)
    merged = identity.merge(
        docs[version]["document_id"], docs[other]["document_id"], [version, other]
    )
    lifecycle = Lifecycle(db)
    target = docs[other]["document_id"]
    with db.transaction() as conn:
        conn.execute("UPDATE document_versions SET visibility='hidden' WHERE id=?", (other,))
    lifecycle.update(target, 0, "retracted", "test flag")
    with pytest.raises(EngineError, match="IDENTITY_CONFLICT"):
        identity.undo(merged["id"])
    lifecycle.update(target, 1, "active", "restore prior visibility")
    with db.connection() as conn:
        states = dict(conn.execute("SELECT id,visibility FROM document_versions"))
    assert states[other] == "hidden" and states[version] == "visible"
    identity.undo(merged["id"])


def test_local_answer_candidate_quota_uses_logical_papers_not_pdf_versions(store):
    from ragsystem.library.identity import Identity

    root, db, version = store
    other = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/2020.emnlp-main.550.pdf", "dpr"
    )["doc_version_id"]
    docs = {row["doc_version_id"]: row for row in Library(db).list_documents()}
    search = HybridSearch(db, root)
    hits = [{"doc_version_id": version, "chunk_id": str(i)} for i in range(7)] + [
        {"doc_version_id": other, "chunk_id": "other"}
    ]
    assert len(search.paper_quota(hits, 8, 3)) == 4
    Identity(db).merge(docs[version]["document_id"], docs[other]["document_id"], [version, other])
    assert len(search.paper_quota(hits, 8, 3)) == 3


def test_schema9_to10_migration_keeps_exact_upgrade_backup(tmp_path):
    import hashlib
    import sqlite3

    from ragsystem.storage.database import SCHEMA_VERSION

    path = tmp_path / "data/research.db"
    path.parent.mkdir()
    scripts = sorted((ROOT / "engine/ragsystem/storage/migrations").glob("*.sql"))
    with sqlite3.connect(path) as conn:
        for file in scripts:
            version = int(file.name.split("_")[0])
            if version > 9:
                break
            script = file.read_text()
            conn.executescript(script)
            conn.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (version, hashlib.sha256(script.encode()).hexdigest(), "2026-10-24T00:00:00+00:00"),
            )
            conn.execute(f"PRAGMA user_version={version}")
            conn.commit()
    db = Database(path)
    with db.connection() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='document_lifecycle'"
            ).fetchone()[0]
            == 1
        )
    snapshots = list((path.parent / "migration-backups").glob("before-v9-*.db"))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='document_lifecycle'"
            ).fetchone()[0]
            == 0
        )
