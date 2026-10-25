import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.server import AnnotationRequest, create_app
from ragsystem.library.annotations import Annotations
from ragsystem.library.identity import Identity
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.database import Database

ROOT = Path(__file__).resolve().parents[2]


def test_manual_identity_merge_preserves_sources_projects_and_guarded_undo(tmp_path):
    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    importer = PdfImporter(db, root)
    one = importer.import_path_for_test(ROOT / "tests/fixtures/public/N19-1423.pdf", "one")
    two = importer.import_path_for_test(
        ROOT / "tests/fixtures/public/2020.emnlp-main.550.pdf", "two"
    )
    Parser(db, root).parse(one["doc_version_id"], "parse")
    library = Library(db)
    docs = library.list_documents()
    source = next(
        row["document_id"] for row in docs if row["doc_version_id"] == one["doc_version_id"]
    )
    target = next(
        row["document_id"] for row in docs if row["doc_version_id"] == two["doc_version_id"]
    )
    project = library.create_project("甲")
    library.set_membership(project["id"], source, True)
    anchor = Sources(db, root).search("BERT", [one["doc_version_id"]], 1)[0]["source_anchor_id"]
    identity = Identity(db)
    merge = identity.merge(source, target, [one["doc_version_id"], two["doc_version_id"]])
    assert len({row["document_id"] for row in library.list_documents()}) == 1
    assert len(library.list_documents(project["id"])) == 2
    assert Sources(db, root).anchor(anchor)["doc_version_id"] == one["doc_version_id"]
    identity.undo(merge["id"])
    assert len({row["document_id"] for row in library.list_documents()}) == 2
    assert len(library.list_documents(project["id"])) == 1
    merge = identity.merge(source, target, [one["doc_version_id"], two["doc_version_id"]])
    library.set_membership(project["id"], target, False)
    with pytest.raises(EngineError, match="IDENTITY_CONFLICT"):
        identity.undo(merge["id"])
    assert len(list((root / "papers").glob("*.pdf"))) == 2


def test_unparsed_pdf_notes_page_bounds_history_and_no_evidence_pollution(tmp_path):
    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "one"
    )["doc_version_id"]
    notes = Annotations(db, root)
    saved = notes.save(
        version, AnnotationRequest(expected_revision=0, page_number=16, note="我的阅读笔记")
    )
    notes.save(
        version,
        AnnotationRequest(
            annotation_id=saved["id"], expected_revision=1, page_number=16, note="第二次核对"
        ),
    )
    with pytest.raises(EngineError, match="ANNOTATION_CONFLICT"):
        notes.save(
            version,
            AnnotationRequest(
                annotation_id=saved["id"], expected_revision=1, page_number=16, note="过时修改"
            ),
        )
    with pytest.raises(EngineError, match="SOURCE_PAGE_INVALID"):
        notes.save(
            version, AnnotationRequest(expected_revision=0, page_number=17, note="不存在的页")
        )
    reopened = Annotations(Database(db.path), root).list(version)
    assert reopened[0]["note"] == "第二次核对" and len(reopened[0]["history"]) == 2
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM evidence_records").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0


def test_batch_import_idempotency_project_and_duplicate_sha(tmp_path):
    root = tmp_path / "store"
    token = secrets.token_hex(32)
    headers = {"X-RAG-Session": token}
    with TestClient(create_app(token, root), base_url="http://127.0.0.1") as client:
        project = client.post("/v0/projects", json={"name": "批量项目"}, headers=headers).json()
        grants = [
            client.post(
                "/v0/internal/file-grants",
                json={"path": str(ROOT / "tests/fixtures/public" / name)},
                headers=headers,
            ).json()["file_grant_id"]
            for name in ["N19-1423.pdf", "2020.emnlp-main.550.pdf", "N19-1423.pdf"]
        ]
        body = {"file_grant_ids": grants, "idempotency_key": "batch", "project_id": project["id"]}
        first = client.post("/v0/import-batches", json=body, headers=headers)
        assert first.status_code == 202 and len(first.json()["jobs"]) == 3
        repeat = client.post("/v0/import-batches", json=body, headers=headers)
        assert [row["job_id"] for row in repeat.json()["jobs"]] == [
            row["job_id"] for row in first.json()["jobs"]
        ]
        docs = client.get(
            "/v0/documents", params={"project_id": project["id"]}, headers=headers
        ).json()["documents"]
        assert len(docs) == 2
        jobs = client.get("/v0/jobs", headers=headers).json()["jobs"]
        assert all(job["status"] == "completed" for job in jobs)
        assert (
            client.post(
                "/v0/import-batches",
                json={**body, "file_grant_ids": [grants[0], grants[0]]},
                headers=headers,
            ).status_code
            == 400
        )
