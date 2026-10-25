"""Candidate integration and failure fencing; not a scientific table gold set."""

import json
import os
import secrets
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.library.repository import Library
from ragsystem.parsing.docling import (
    DoclingService,
    serialize_document,
    verify_directory,
)
from ragsystem.parsing.pipeline import Parser
from ragsystem.parsing.process import run_worker
from ragsystem.parsing.tables import Tables
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import Database
from ragsystem.workflows.workbench import Workbench

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def model_directory():
    value = os.environ.get("RAGSYSTEM_DOCLING_MODEL_DIR")
    if not value:
        pytest.skip("explicit approved layout/table resources and optional runtime required")
    return Path(value).resolve()


def test_actual_docling_publish_table_spans_reviews_citations_and_restore(
    tmp_path, model_directory
):
    root = tmp_path / "表格 中文 空格"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "bert"
    )["doc_version_id"]
    jobs = Jobs(db)
    load = jobs.enqueue("verify", "docling", {"action": "configure_docling"})
    service = DoclingService(db)
    service.configure(Directories().issue(model_directory, "docling"), jobs.claim(load["id"]))
    assert service.status()["configured"] and "directory" not in service.status()
    Parser(db, root).parse(version, "structured", use_docling=True)
    tables = Tables(db)
    index = tables.list(version)
    assert index["total"] > 0
    cell_total = 0
    with db.connection() as conn:
        for row in conn.execute(
            "SELECT c.*,e.raw_text FROM table_cells c JOIN parse_tables t ON t.id=c.table_id JOIN elements e ON e.id=t.element_id"
        ):
            assert row["raw_text"][row["start_offset"] : row["end_offset"]] == row["text"]
            cell_total += 1
        assert cell_total > 10
        chunks = conn.execute("SELECT * FROM chunks WHERE visible=1").fetchall()
        for chunk in chunks:
            text = conn.execute(
                "SELECT raw_text FROM elements WHERE id=?", (chunk["element_id"],)
            ).fetchone()[0]
            assert text[chunk["start_offset"] : chunk["end_offset"]] == chunk["clean_text"]
        # Pick real non-empty cell text fully contained in one exact chunk.
        selected = conn.execute(
            """SELECT c.id AS chunk_id,c.clean_text,tc.text FROM chunks c JOIN parse_tables t ON t.element_id=c.element_id JOIN table_cells tc ON tc.table_id=t.id WHERE LENGTH(tc.text)>2 AND tc.start_offset>=c.start_offset AND tc.end_offset<=c.end_offset LIMIT 1"""
        ).fetchone()
    assert selected
    work = Workbench(db, root, HybridSearch(db, root))
    with db.transaction() as conn:
        evidence_id = work.evidence(
            conn,
            "table-test",
            selected["chunk_id"],
            selected["text"],
            {selected["chunk_id"]: selected["clean_text"]},
        )
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM evidence_records WHERE id=?", (evidence_id,)).fetchone()
    evidence = work.public_evidence(row)
    assert (
        evidence["table_candidates"]
        and evidence["text_origin"] == "docling_layout_table_unreviewed"
    )
    anchor = Sources(db, root).anchor(selected["chunk_id"])
    assert anchor["bbox_norm"] is None and anchor["location_level"] == "page_only"
    table_id = evidence["table_candidates"][0]["table_id"]
    table = tables.get(table_id)
    assert table["review"]["revision"] == 0 and table["scientific_comparability"] == "not_assessed"
    tables.review(
        table_id,
        SimpleNamespace(
            expected_revision=0, status="uncertain", note="工程试验；列对齐尚未科研验收"
        ),
    )
    with pytest.raises(EngineError, match="REVIEW_CONFLICT"):
        tables.review(
            table_id,
            SimpleNamespace(expected_revision=0, status="confirmed", note="stale"),
        )
    assert tables.get(table_id)["review"]["status"] == "uncertain"
    # Sparse original page numbers must not be renumbered by page-range runs.
    # Leave the reviewed table page untouched; keep its cells and review IDs.
    preserved = tables.get(table_id)
    untouched = preserved["page_number"]
    selected_pages = [p for p in [6, 8, 16] if p != untouched]
    before = {
        p["page_number"]: p["parse_run_id"] for p in Library(db).parse_diagnostics(version)["pages"]
    }
    Parser(db, root).parse(
        version, "sparse-structure", use_docling=True, page_numbers=selected_pages
    )
    assert tables.get(table_id) == preserved
    with db.connection() as conn:
        after = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT p.page_number,e.parse_run_id FROM published_pages p JOIN elements e ON e.id=p.element_id"
            )
        }
    assert {n for n in before if before[n] != after[n]} == set(selected_pages)
    # Snapshot includes immutable candidate cells and independent review revisions.
    snapshot = Backups(db, root).create(tmp_path / "snapshot")
    restored = tmp_path / "restored"
    Backups.restore(snapshot, restored)
    restored_db = Database(restored / "data/research.db")
    assert Tables(restored_db).get(table_id) == tables.get(table_id)
    assert db.integrity()["foreign_key_check"] == []
    previous = Sources(db, root).anchor(selected["chunk_id"])
    with db.transaction() as conn:
        config = json.loads(
            conn.execute("SELECT value_json FROM app_settings WHERE key='docling'").fetchone()[0]
        )
        config["fingerprint"]["runtimes"]["torch"] = "changed"
        conn.execute(
            "UPDATE app_settings SET value_json=? WHERE key='docling'",
            (json.dumps(config),),
        )
    with pytest.raises(EngineError, match="DOCLING_FINGERPRINT_CHANGED"):
        Parser(db, root).parse(version, "bad-runtime", use_docling=True)
    assert Sources(db, root).anchor(selected["chunk_id"]) == previous
    # Reparse invalidates tables for new reads/reviews; old rows and audit remain.
    Parser(db, root).parse(version, "fast")
    assert tables.list(version)["total"] == 0
    with pytest.raises(EngineError, match="SCOPE_STALE"):
        tables.get(table_id)


def test_docling_limits_before_model_loading_and_cancellation(tmp_path, model_directory):
    import pypdfium2 as pdfium

    directory = tmp_path / "logs"
    for name, sizes, code in [
        ("oversize", [(20000, 20000)], "DOCLING_PIXEL_LIMIT"),
        ("pages", [(100, 100)] * 41, "DOCLING_PAGE_LIMIT"),
    ]:
        path = tmp_path / (name + ".pdf")
        with pdfium.PdfDocument.new() as pdf:
            for width, height in sizes:
                pdf.new_page(width, height).close()
            pdf.save(path)
        with pytest.raises(EngineError, match=code):
            run_worker(
                {
                    "docling_directory": str(model_directory),
                    "pdf_path": str(path),
                    "docling_fingerprint": {},
                },
                log_directory=directory,
            )
    db = Database(tmp_path / "data/research.db")
    jobs = Jobs(db)
    row = jobs.enqueue("verify", "cancel", {})
    job = jobs.claim(row["id"])
    jobs.cancel(job["id"])
    with pytest.raises(EngineError, match="LEASE_LOST"):
        DoclingService(db).configure(Directories().issue(model_directory, "docling"), job)
    assert not DoclingService(db).status()["configured"]


def test_docling_authorization_strict_input_and_table_http(tmp_path):
    resource = tmp_path / "resources"
    resource.mkdir()
    directories = Directories()
    grant = directories.issue(resource, "ocr")
    with pytest.raises(EngineError, match="GRANT_INVALID"):
        directories.take(grant.id, "docling")
    with pytest.raises(EngineError):
        verify_directory(resource)
    root = tmp_path / "workspace"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "bert"
    )["doc_version_id"]
    token = secrets.token_hex(32)
    with TestClient(create_app(token, root), base_url="http://127.0.0.1") as client:
        assert client.get("/v0/docling").status_code == 401
        client.headers["X-RAG-Session"] = token
        assert not client.get("/v0/docling").json()["configured"]
        assert (
            client.post(
                "/v0/docling",
                json={
                    "model_grant_id": "fake",
                    "path": str(resource),
                    "idempotency_key": "invalid",
                },
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/v0/documents/{version}/parse",
                json={"use_docling": True, "idempotency_key": "layout"},
            ).json()["code"]
            == "DOCLING_NOT_CONFIGURED"
        )
        assert (
            client.post(
                f"/v0/documents/{version}/parse",
                json={
                    "use_docling": True,
                    "use_ocr": True,
                    "idempotency_key": "conflict",
                },
            ).json()["code"]
            == "PARSER_OPTIONS_CONFLICT"
        )
        assert client.get(f"/v0/documents/{version}/tables").json()["total"] == 0
        assert client.get(f"/v0/documents/{version}/tables?offset=-1").status_code == 400


def test_tampered_fixed_configuration_is_rejected_before_model_load(tmp_path, model_directory):
    relative = Path("docling-project--docling-layout-heron/config.json")
    target = tmp_path / relative
    target.parent.mkdir()
    data = (model_directory / relative).read_bytes()
    target.write_bytes(b"X" + data[1:])
    with pytest.raises(EngineError, match="DOCLING_MODEL_HASH_MISMATCH"):
        verify_directory(tmp_path)


def test_table_alignment_failure_rolls_back_replacement_and_keeps_old_anchor(tmp_path, monkeypatch):
    root = tmp_path / "transaction"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "bert"
    )["doc_version_id"]
    parser = Parser(db, root)
    parser.parse(version, "initial")
    sources = Sources(db, root)
    hit = sources.search("BERT", [version], 1)[0]
    anchor = sources.anchor(hit["source_anchor_id"])
    # Engineering fault fixture only: wrong cell->element offsets after old text
    # has been withdrawn inside the uncommitted replacement transaction.
    content = {
        "pages": [
            {
                "page_number": 1,
                "text": "real text",
                "error_code": None,
                "rotation": 0,
                "method": "docling",
                "blocks": [],
            }
        ],
        "tables": [
            {
                "page_number": 1,
                "source_ref": "#/tables/0",
                "source_pages": [1],
                "rows": 1,
                "columns": 1,
                "raw": {},
                "cells": [
                    {
                        "row": 0,
                        "row_end": 1,
                        "column": 0,
                        "column_end": 1,
                        "text": "forged",
                        "start": 0,
                        "end": 6,
                        "column_header": False,
                        "row_header": False,
                        "raw": {},
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr("ragsystem.parsing.pipeline.run_worker", lambda *args, **kwargs: content)
    with pytest.raises(EngineError, match="SOURCE_ALIGNMENT_INVALID"):
        parser.parse(version, "bad-mapping")
    assert sources.anchor(hit["source_anchor_id"]) == anchor
    assert Tables(db).list(version)["total"] == 0
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM parse_tables").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM parse_page_structure").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT status FROM parse_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()[0]
            == "failed"
        )


def test_unresolved_multpage_table_and_valid_text_charspans_are_not_fabricated():
    class Item:
        def __init__(self, data):
            self.data = data

        def model_dump(self, **kwargs):
            return self.data

    text = {
        "self_ref": "#/texts/0",
        "label": "text",
        "text": "甲乙丙丁",
        "prov": [
            {"page_no": 1, "charspan": [0, 2]},
            {"page_no": 2, "charspan": [2, 4]},
        ],
    }
    table = {
        "self_ref": "#/tables/0",
        "label": "table",
        "prov": [{"page_no": 1}, {"page_no": 2}],
        "data": {
            "num_rows": 1,
            "num_cols": 1,
            "table_cells": [
                {
                    "text": "uncertain",
                    "start_row_offset_idx": 0,
                    "end_row_offset_idx": 1,
                    "start_col_offset_idx": 0,
                    "end_col_offset_idx": 1,
                }
            ],
        },
    }
    document = SimpleNamespace(iterate_items=lambda: iter([(Item(text), 0), (Item(table), 0)]))
    result = serialize_document(document, 2, [0, 90])
    assert result["pages"][0]["text"] == "甲乙\n" and result["pages"][1]["text"] == "丙丁\n"
    assert result["tables"][0]["page_number"] is None
    assert result["tables"][0]["cells"][0]["start"] is None
    assert all(page["error_code"] == "DOCLING_ITEM_LOCATION_UNRESOLVED" for page in result["pages"])
    text["prov"][1]["charspan"] = [1, 4]
    result = serialize_document(document, 2, [0, 0])
    assert all(not page["text"] for page in result["pages"])
    assert result["unresolved_items"] == 2
    table["prov"] = []
    result = serialize_document(document, 2, [0, 0])
    assert result["unresolved_items"] == 2
    assert result["tables"][0]["page_number"] is None
