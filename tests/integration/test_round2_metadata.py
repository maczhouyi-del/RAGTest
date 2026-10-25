"""Real public PDF extraction plus explicit rule/failure fixtures, no LLM/network."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.library.metadata import VERSION, MetadataExtraction, extract_candidates
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import Database
from test_mvp_core import store


def test_real_pdf_candidates_manual_precedence_duplicate_reparse_restore(tmp_path):
    root, db, version = store(tmp_path)
    extractor, library = MetadataExtraction(db, root), Library(db)
    assert extractor.run_one() and not extractor.run_one()
    doc = library.list_documents()[0]
    assert doc["title"].startswith("BERT: Pre-training")
    assert doc["authors"] == [
        "Jacob Devlin",
        "Ming-Wei Chang",
        "Kenton Lee",
        "Kristina Toutanova",
    ]
    assert doc["year"] == 2019 and doc["venue"] == "Proceedings of NAACL-HLT 2019"
    assert "We introduce" in doc["abstract"] and doc["doi"] is None
    assert doc["metadata_candidates"]["abstract"]["source_page"] == 1
    assert doc["metadata_pending"]
    saved = library.update_metadata(
        doc["document_id"],
        {
            "expected_revision": 0,
            "title": "人工题名",
            "abstract": "人工修订摘要",
            "field_actions": {
                "title": "manual",
                "abstract": "manual",
                "year": "confirm",
            },
        },
    )
    assert saved["metadata_origins"]["year"] == "confirmed"
    assert saved["authors"] == doc["authors"]
    Parser(db, root).parse(version, "reparse")
    PdfImporter(db, root).import_path_for_test(
        Path(__file__).resolve().parents[2] / "tests/fixtures/public/N19-1423.pdf",
        "duplicate",
    )
    extractor.ensure_missing()
    assert not extractor.run_one()
    with db.connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM jobs WHERE idempotency_key=?",
                (VERSION + ":" + version,),
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute("SELECT count(*) FROM metadata_candidates").fetchone()[0] == 5
        )
    reopened = Library(Database(db.path)).list_documents()[0]
    assert reopened["title"] == "人工题名" and reopened["abstract"] == "人工修订摘要"
    adopted = library.update_metadata(
        doc["document_id"],
        {
            "expected_revision": 1,
            "title": reopened["title"],
            "field_actions": {"title": doc["metadata_candidates"]["title"]["id"]},
        },
    )
    assert adopted["title"] == doc["title"] and adopted["abstract"] == "人工修订摘要"
    snapshot = Backups(db, root).create(tmp_path / "backups")
    restored = tmp_path / "restored"
    Backups.restore(snapshot, restored)
    assert (
        Library(Database(restored / "data/research.db")).list_documents()
        == library.list_documents()
    )


def test_rules_do_not_use_creation_date_filename_or_unbounded_abstract():
    candidates = extract_candidates(
        {
            "CreationDate": "D:20261025",
            "Title": "draft.docx",
            "Author": "Microsoft Word",
        },
        [
            {
                "page_number": 1,
                "text": "Random text mentions Smith (2020).\nAbstract\nNo clear end marker.",
            }
        ],
    )
    assert candidates == {}
    candidates = extract_candidates(
        {},
        [
            {
                "page_number": 1,
                "text": "Title: An explicitly labeled real paper title\ndoi:10.1234/Verified.Value\nAbstract\n"
                + "Original abstract sentence. " * 5
                + "\n1 Introduction\nbody",
            }
        ],
    )
    assert candidates["doi"]["value"] == "10.1234/verified.value"
    assert "year" not in candidates and "authors" not in candidates
    assert candidates["abstract"]["value"].startswith("Original abstract")


def test_metadata_failure_does_not_affect_original_parse_and_retry(
    tmp_path, monkeypatch
):
    root, db, version = store(tmp_path)
    import ragsystem.library.metadata as module

    original = module.run_worker

    def fail(*args, **kwargs):
        raise RuntimeError("explicit failure fixture")

    monkeypatch.setattr(module, "run_worker", fail)
    extractor = MetadataExtraction(db, root)
    assert extractor.run_one()
    assert Library(db).list_documents()[0]["metadata_extraction"]["status"] == "failed"
    Parser(db, root).parse(version, "parse-despite-metadata-failure")
    assert Library(db).list_documents()[0]["parse_status"] == "ready"
    assert Library(db).file_record(version, root)["file_sha256"]
    job = Jobs(db).find_key("verify", VERSION + ":" + version)
    Jobs(db).retry(job["id"])
    monkeypatch.setattr(module, "run_worker", original)
    assert extractor.run_one()
    assert (
        Library(db).list_documents()[0]["metadata_extraction"]["status"] == "completed"
    )


def test_restart_engine_recovers_without_frontend(tmp_path):
    root, db, version = store(tmp_path)
    # Durable intent exists before any React UI/HTTP request. Startup pump completes it.
    with TestClient(
        create_app("b" * 64, root),
        base_url="http://127.0.0.1",
        headers={"X-RAG-Session": "b" * 64},
    ) as client:
        for _ in range(100):
            doc = client.get("/v0/documents").json()["documents"][0]
            if doc["metadata_extraction"]["status"] == "completed":
                break
            time.sleep(0.05)
        assert (
            doc["year"] == 2019 and doc["metadata_candidates"]["year"]["source_excerpt"]
        )
    with TestClient(
        create_app("b" * 64, root),
        base_url="http://127.0.0.1",
        headers={"X-RAG-Session": "b" * 64},
    ) as client:
        again = client.get("/v0/documents").json()["documents"][0]
        assert again["metadata_candidates"] == doc["metadata_candidates"]
        assert again["metadata_extraction"]["status"] == "completed"


def test_legacy_manual_values_survive_later_automatic_candidates(tmp_path):
    root, db, version = store(tmp_path)
    library = Library(db)
    doc = library.list_documents()[0]
    saved = library.update_metadata(
        doc["document_id"],
        {
            "expected_revision": 0,
            "title": "已有人工题名",
            "authors": ["人工作者"],
            "year": 2021,
            "venue": "人工会议",
            "doi": "10.1234/manual",
        },
    )
    MetadataExtraction(db, root).run_one()
    after = library.list_documents()[0]
    assert all(
        after[field] == saved[field]
        for field in ["title", "authors", "year", "venue", "doi"]
    )
    assert after["metadata_candidates"]["year"]["value"] == 2019
    assert after["abstract"].startswith("We introduce")


def test_candidate_edit_rejects_other_document_version(tmp_path):
    from ragsystem.domain.errors import EngineError

    root, db, version = store(tmp_path)
    MetadataExtraction(db, root).run_one()
    doc = Library(db).list_documents()[0]
    with pytest.raises(EngineError, match="NOT_FOUND"):
        Library(db).update_metadata(
            doc["document_id"],
            {
                "expected_revision": 0,
                "title": "bad version",
                "doc_version_id": "different-version",
                "field_actions": {"title": "manual"},
            },
        )


def test_embedded_fields_share_manual_validation_without_guessing_names():
    from ragsystem.library.metadata import extract_candidates

    valid = extract_candidates(
        {"Author": "Jane Doe\nJohn Smith", "Title": "A valid embedded paper title"}, []
    )
    assert valid["authors"]["value"] == ["Jane Doe", "John Smith"]
    invalid = extract_candidates(
        {"Author": "Bad\x00Name", "Title": "A paper title with\x00control"}, []
    )
    assert invalid == {}
