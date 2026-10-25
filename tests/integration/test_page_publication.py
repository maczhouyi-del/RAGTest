"""Publication safety with real native PDFs and explicitly synthetic fault outputs."""

import hashlib
import json
import secrets
import sqlite3
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.parsing.routing import accept, choose, probe
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import Database
from ragsystem.storage.workspace_lock import WorkspaceLock
from ragsystem.workflows.workbench import Workbench

ROOT = Path(__file__).resolve().parents[2]


def workspace(tmp_path):
    root = tmp_path / "按页 中文 空格"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "bert"
    )["doc_version_id"]
    return root, db, version, Parser(db, root)


def pointers(db):
    with db.connection() as conn:
        return dict(conn.execute("SELECT page_number,element_id FROM published_pages"))


def test_selective_native_publish_preserves_untouched_ids_and_scope(tmp_path):
    root, db, version, parser = workspace(tmp_path)
    parser.parse(version, "base")
    before = pointers(db)
    with db.connection() as conn:
        chunks = [dict(r) for r in conn.execute("SELECT * FROM chunks WHERE visible=1")]
    work = Workbench(db, root, HybridSearch(db, root))
    scope = work.scope(work.freeze([version], None))
    job = parser.parse(version, "page-2-4", page_numbers=[4, 2])
    assert parser.parse(version, "page-2-4", page_numbers=[2, 4]) == job
    after = pointers(db)
    assert len(after) == 16
    assert {n for n in before if before[n] != after[n]} == {2, 4}
    assert work.current_runs(version) != scope["versions"][0]["parse_run_ids"]
    source = Sources(db, root)
    for chunk in chunks:
        if chunk["page_number"] in {2, 4}:
            with pytest.raises(EngineError, match="NOT_FOUND"):
                source.anchor(chunk["id"])
        else:
            assert source.anchor(chunk["id"])["source_anchor_id"] == chunk["id"]
    backup = Backups(db, root).create(tmp_path / "backup")
    restored = tmp_path / "restored"
    Backups.restore(backup, restored)
    assert pointers(Database(restored / "data/research.db")) == after
    assert db.integrity()["foreign_key_check"] == []


def test_queued_revision_and_replayed_options_are_fenced(tmp_path):
    _, db, version, parser = workspace(tmp_path)
    with pytest.raises(EngineError, match="PARTIAL_PARSE_NEEDS_BASE"):
        parser.parse(version, "no-base", page_numbers=[1])
    parser.parse(version, "base")
    queued = parser.parse(version, "queued", queue_only=True, page_numbers=[3])
    parser.parse(version, "another", page_numbers=[2])
    before = pointers(db)
    with pytest.raises(EngineError, match="PARSE_PUBLICATION_CHANGED"):
        parser.parse(version, "queued", page_numbers=[3])
    assert Jobs(db).get(queued["id"])["status"] == "queued"
    with pytest.raises(EngineError, match="IDEMPOTENCY_CONFLICT"):
        parser.parse(version, "base", page_numbers=[1])
    assert pointers(db) == before


def test_answer_commit_rechecks_scope_when_an_unretrieved_page_changes(tmp_path, monkeypatch):
    root, db, version, parser = workspace(tmp_path)
    parser.parse(version, "base")
    work = Workbench(db, root, HybridSearch(db, root))
    answer = work.create_answer("BERT", [version], None, "extractive", "keyword")
    original = work.search.search

    def update_after_retrieval(*args, **kwargs):
        result = original(*args, **kwargs)
        # Deliberately change a page outside this concrete retrieved result set.
        pages = {r["page_number"] for r in result["results"]}
        page = next(n for n in range(1, 17) if n not in pages)
        parser.parse(version, "changed-during-answer", page_numbers=[page])
        return result

    monkeypatch.setattr(work.search, "search", update_after_retrieval)
    work.run_answer(answer["id"])
    with db.connection() as conn:
        row = conn.execute(
            "SELECT status,error_code FROM answer_runs WHERE id=?", (answer["id"],)
        ).fetchone()
        assert row["status"] == "failed" and row["error_code"] == "SCOPE_STALE"
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM evidence_records WHERE owner_id=?", (answer["id"],)
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("pages", [[], [True], [1, 1], [0], [501], list(range(1, 42)), "1"])
def test_invalid_selection_has_no_side_effects(tmp_path, pages):
    _, db, version, parser = workspace(tmp_path)
    with pytest.raises(EngineError, match="INVALID_PARSE_PAGES"):
        parser.parse(version, "invalid", page_numbers=pages)
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs WHERE type='parse_page'").fetchone()[0] == 0


def test_publication_race_rolls_back_and_retains_attempt_output(tmp_path, monkeypatch):
    _, db, version, parser = workspace(tmp_path)
    parser.parse(version, "base")
    import ragsystem.parsing.pipeline as pipeline

    original = pipeline.run_worker
    winner = {}

    def concurrent_publication(*args, **kwargs):
        content = original(*args, **kwargs)
        monkeypatch.setattr(pipeline, "run_worker", original)
        parser.parse(version, "winner", page_numbers=[4])
        winner.update(pointers(db))
        return content

    monkeypatch.setattr(pipeline, "run_worker", concurrent_publication)
    with pytest.raises(EngineError, match="PARSE_PUBLICATION_CHANGED"):
        parser.parse(version, "loser", page_numbers=[2])
    assert pointers(db) == winner
    with db.connection() as conn:
        attempt = conn.execute(
            "SELECT a.* FROM parse_attempts a JOIN parse_runs r ON r.id=a.parse_run_id WHERE r.error_code='PARSE_PUBLICATION_CHANGED'"
        ).fetchone()
        assert attempt["status"] == "completed" and json.loads(attempt["result_json"])["pages"]


def test_unlocated_gap_survives_partial_reparse_until_whole_reparse(tmp_path, monkeypatch):
    _, db, version, parser = workspace(tmp_path)
    import ragsystem.parsing.pipeline as pipeline

    original = pipeline.run_worker

    def unlocated(*args, **kwargs):
        return {
            **original(*args, **kwargs),
            "unresolved_items": 1,
            "unlocated_items": [{"raw": "unlocated fault fixture"}],
        }

    monkeypatch.setattr(pipeline, "run_worker", unlocated)
    parser.parse(version, "unknown-location")
    monkeypatch.setattr(pipeline, "run_worker", original)
    parser.parse(version, "selective", page_numbers=[1])
    assert PdfImporter(db, tmp_path / "unused").list_documents()[0]["parse_status"] == "partial"
    with db.connection() as conn:
        assert conn.execute("SELECT unlocated_items FROM parse_state").fetchone()[0] == 1
    parser.parse(version, "whole")
    with db.connection() as conn:
        assert conn.execute("SELECT unlocated_items FROM parse_state").fetchone()[0] == 0


def test_blank_pages_are_published_and_participate_in_frozen_scope(tmp_path):
    source = tmp_path / "blank.pdf"
    with pdfium.PdfDocument.new() as pdf:
        pdf.new_page(400, 600).close()
        pdf.new_page(400, 600).close()
        pdf.save(source)
    root = tmp_path / "root"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(source, "blank")["doc_version_id"]
    parser = Parser(db, root)
    parser.parse(version, "whole")
    work = Workbench(db, root, HybridSearch(db, root))
    old = work.current_runs(version)
    assert len(old) == 1
    parser.parse(version, "page", page_numbers=[2])
    assert len(work.current_runs(version)) == 2
    assert len(pointers(db)) == 2 and Library(db).parse_diagnostics(version)["needs_ocr_pages"] == [
        1,
        2,
    ]


def test_real_geometry_probe_routes_without_resources_and_records_audit(tmp_path):
    _, db, version, parser = workspace(tmp_path)
    with pdfium.PdfDocument(ROOT / "tests/fixtures/public/N19-1423.pdf") as pdf:
        page = pdf[6]
        text = page.get_textpage()
        signals = probe(page, text, text.get_text_range())
        assert signals["multi_column_candidate"] or signals["numeric_grid_candidate"]
        text.close()
        page.close()
    parser.parse(version, "base")
    parser.parse(version, "auto-no-resources", auto_enhance=True, page_numbers=[7])
    diagnostics = Library(db).parse_diagnostics(version)
    routing = diagnostics["runs"][0]["routing"]
    assert routing[0]["desired_method"] == "docling" and routing[0]["reason"].startswith(
        "RESOURCE_NOT_CONFIGURED"
    )
    assert (
        next(p for p in diagnostics["pages"] if p["page_number"] == 7)["error_code"]
        == "AUTO_ENHANCEMENT_UNAVAILABLE"
    )
    assert len(diagnostics["runs"][0]["attempts"]) == 1


def test_auto_enhancement_failure_rejection_and_cancel_are_distinct(tmp_path, monkeypatch):
    _, db, version, parser = workspace(tmp_path)
    parser.parse(version, "base")
    monkeypatch.setattr(
        "ragsystem.parsing.pipeline.DoclingService.status", lambda _: {"configured": True}
    )
    monkeypatch.setattr(
        "ragsystem.parsing.pipeline.DoclingService.require",
        lambda _: {"directory": "synthetic-fault-only", "fingerprint": {"pipeline": "fault"}},
    )
    import ragsystem.parsing.pipeline as pipeline

    original = pipeline.run_worker

    def broken(request, **kwargs):
        if request.get("docling_directory"):
            raise EngineError("DOCLING_CONVERSION_INCOMPLETE")
        return original(request, **kwargs)

    monkeypatch.setattr(pipeline, "run_worker", broken)
    parser.parse(version, "fallback", auto_enhance=True, page_numbers=[7])
    diag = Library(db).parse_diagnostics(version)
    assert diag["runs"][0]["routing"][0]["enhancement_error"] == "DOCLING_CONVERSION_INCOMPLETE"
    assert any(a["status"] == "failed" for a in diag["runs"][0]["attempts"])
    assert (
        next(p for p in diag["pages"] if p["page_number"] == 7)["error_code"]
        == "AUTO_ENHANCEMENT_FAILED"
    )

    def reduced(request, **kwargs):
        if request.get("docling_directory"):
            return {
                "pages": [
                    {
                        "page_number": 7,
                        "text": "too short",
                        "method": "docling",
                        "rotation": 0,
                        "error_code": None,
                    }
                ]
            }
        return original(request, **kwargs)

    monkeypatch.setattr(pipeline, "run_worker", reduced)
    parser.parse(version, "rejection", auto_enhance=True, page_numbers=[7])
    assert (
        Library(db).parse_diagnostics(version)["runs"][0]["routing"][0]["acceptance_reason"]
        == "TEXT_COVERAGE_DECREASED"
    )
    before = pointers(db)

    def cancelled(request, **kwargs):
        if request.get("docling_directory"):
            raise EngineError("LEASE_LOST")
        return original(request, **kwargs)

    monkeypatch.setattr(pipeline, "run_worker", cancelled)
    with pytest.raises(EngineError, match="LEASE_LOST"):
        parser.parse(version, "cancelled", auto_enhance=True, page_numbers=[7])
    assert pointers(db) == before


def test_route_ocr_precedence_and_acceptance_guard():
    decisions = choose(
        [
            {
                "page_number": 1,
                "text": "garbled enough text" * 5,
                "error_code": None,
                "signals": {
                    "nonspace_chars": 100,
                    "suspicious_ratio": 0.1,
                    "numeric_grid_candidate": True,
                },
            }
        ],
        ocr_available=True,
        docling_available=True,
    )
    assert decisions[0]["method"] == "ocr"
    assert not accept({"text": "long text" * 30}, {"text": "tiny", "method": "docling"})[0]
    assert not accept({"text": ""}, {"text": "read", "method": "ocr", "mean_confidence": 59})[0]


def test_structure_budget_covers_combined_published_pages(tmp_path, monkeypatch):
    _, db, version, parser = workspace(tmp_path)
    parser.parse(version, "base")
    import ragsystem.parsing.pipeline as pipeline

    original = pipeline.run_worker

    def synthetic_table(request, **kwargs):
        content = original(request, **kwargs)
        number = content["pages"][0]["page_number"]
        return {
            **content,
            "tables": [
                {
                    "page_number": number,
                    "source_pages": [number],
                    "source_ref": "#/fault-fixture",
                    "rows": 0,
                    "columns": 0,
                    "cells": [],
                    "raw": {"fixture": True},
                }
            ],
        }

    monkeypatch.setattr(pipeline, "run_worker", synthetic_table)
    monkeypatch.setitem(pipeline.DOCLING_POLICY, "max_tables", 1)
    parser.parse(version, "one-table", page_numbers=[1])
    before = pointers(db)
    with pytest.raises(EngineError, match="DOCLING_STRUCTURE_LIMIT"):
        parser.parse(version, "two-tables", page_numbers=[2])
    assert pointers(db) == before
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM published_tables").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM parse_tables").fetchone()[0] == 1


def test_http_rejects_coercion_duplicate_pages_and_conflicting_modes(tmp_path):
    root, _, version, parser = workspace(tmp_path)
    parser.parse(version, "base")
    token = secrets.token_hex(32)
    with TestClient(
        create_app(token, root), base_url="http://127.0.0.1", headers={"X-RAG-Session": token}
    ) as client:
        for fields in (
            {"page_numbers": [True]},
            {"page_numbers": ["1"]},
            {"auto_enhance": "true"},
            {"page_numbers": [], "path": "untrusted"},
        ):
            response = client.post(
                f"/v0/documents/{version}/parse", json={"idempotency_key": "bad", **fields}
            )
            assert response.status_code == 400 and response.json()["code"] == "INVALID_REQUEST"
        response = client.post(
            f"/v0/documents/{version}/parse",
            json={"idempotency_key": "duplicate", "page_numbers": [1, 1]},
        )
        assert response.json()["code"] == "INVALID_PARSE_PAGES"
        response = client.post(
            f"/v0/documents/{version}/parse",
            json={"idempotency_key": "conflict", "auto_enhance": True, "use_ocr": True},
        )
        assert response.json()["code"] == "PARSER_OPTIONS_CONFLICT"


@pytest.mark.parametrize("restore", [False, True])
def test_interrupted_attempt_reconciles_without_replacing_published_pages(tmp_path, restore):
    root, db, version, parser = workspace(tmp_path)
    parser.parse(version, "base")
    before = pointers(db)
    queued = parser.parse(version, "interrupted", queue_only=True, page_numbers=[1])
    Jobs(db).claim(queued["id"])
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO parse_runs(id,doc_version_id,fingerprint,status,created_at) VALUES('interrupted',?,'fault','running','date')",
            (version,),
        )
        conn.execute(
            "INSERT INTO parse_attempts VALUES('attempt','interrupted','native_text','running','[1]',NULL,NULL,'date',NULL)"
        )
    if restore:
        backup = Backups(db, root).create(tmp_path / "snapshot")
        root = tmp_path / "restored"
        Backups.restore(backup, root)
        db = Database(root / "data/research.db")
        code = "RESTORED_PARSE_INTERRUPTED"
    else:
        lock = WorkspaceLock(root)
        try:
            Jobs(db).recover_owned_workspace(lock)
        finally:
            lock.close()
        code = "ENGINE_RESTARTED"
    assert pointers(db) == before
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM parse_attempts WHERE id='attempt'").fetchone()
        assert row["status"] == "failed" and row["error_code"] == code


def test_v11_upgrade_seeds_latest_pages_including_blanks_and_preserves_snapshot(tmp_path):
    path = tmp_path / "data/research.db"
    path.parent.mkdir()
    migrations = ROOT / "engine/ragsystem/storage/migrations"
    with sqlite3.connect(path) as conn:
        for file in sorted(migrations.glob("*.sql")):
            version = int(file.name.split("_")[0])
            if version > 11:
                break
            script = file.read_text()
            conn.executescript(script)
            conn.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (version, hashlib.sha256(script.encode()).hexdigest(), "2026-10-24"),
            )
            conn.execute(f"PRAGMA user_version={version}")
        conn.execute("INSERT INTO file_assets VALUES(?,1,'paper','date')", ("a" * 64,))
        conn.execute("INSERT INTO documents VALUES('doc','title','date')")
        conn.execute(
            "INSERT INTO document_versions VALUES('version','doc',?,'visible','partial','date')",
            ("a" * 64,),
        )
        conn.execute(
            "INSERT INTO parse_runs(id,doc_version_id,fingerprint,status,page_count,created_at,finished_at) VALUES('run','version','hash','partial',2,'date','date')"
        )
        for number in [1, 2]:
            conn.execute(
                "INSERT INTO elements VALUES(?,?,?,'','needs_ocr_or_review',NULL,0)",
                (f"e{number}", "run", number),
            )
    db = Database(path)
    assert pointers(db) == {1: "e1", 2: "e2"}
    assert len(list((path.parent / "migration-backups").glob("before-v11-*.db"))) == 1
    with db.connection() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    assert db.integrity()["foreign_key_check"] == []
