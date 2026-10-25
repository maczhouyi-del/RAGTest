import hashlib
import secrets
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.server import create_app
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import SCHEMA_VERSION, Database

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "项目 空格"
    db = Database(root / "data/research.db")
    imported = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "one"
    )
    library = Library(db)
    document = library.list_documents()[0]
    return root, db, library, imported, document


def metadata(title="BERT 人工题名", **overrides):
    return {
        "expected_revision": 0,
        "title": title,
        "authors": ["Jacob Devlin"],
        "year": 2019,
        "doi": "https://doi.org/10.18653/v1/N19-1423",
        "venue": "NAACL",
        "tags": ["预训练", "阅读中"],
        **overrides,
    }


def test_one_pdf_in_multiple_projects_is_persistent_and_does_not_duplicate(workspace):
    root, db, library, imported, document = workspace
    one, two = library.create_project(" 中文项目 "), library.create_project("Project B")
    for _ in range(2):
        library.set_membership(one["id"], document["document_id"], True)
    library.set_membership(two["id"], document["document_id"], True)
    PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "duplicate"
    )
    reopened = Library(Database(db.path))
    assert len(reopened.list_documents()) == 1
    assert set(reopened.list_documents()[0]["project_ids"]) == {one["id"], two["id"]}
    assert reopened.list_projects()[0]["document_count"] == 1
    digest = imported["file_sha256"]
    assert hashlib.sha256((root / "papers" / (digest + ".pdf")).read_bytes()).hexdigest() == digest
    library.set_membership(one["id"], document["document_id"], False)
    assert library.list_documents(one["id"]) == []
    assert len(library.list_documents(two["id"])) == 1
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM project_documents").fetchone()[0] == 2


def test_metadata_conflict_does_not_overwrite_or_reparse_and_survives_restore(workspace):
    root, db, library, imported, document = workspace
    Parser(db, root).parse(imported["doc_version_id"], "parse")
    with db.connection() as conn:
        chunks = [tuple(row) for row in conn.execute("SELECT * FROM chunks ORDER BY id")]
    saved = library.update_metadata(document["document_id"], metadata())
    assert saved["metadata_revision"] == 1
    assert saved["doi"] == "10.18653/v1/n19-1423"
    with pytest.raises(EngineError, match="METADATA_CONFLICT"):
        library.update_metadata(document["document_id"], metadata("stale edit"))
    assert library.list_documents()[0]["title"] == "BERT 人工题名"
    with db.connection() as conn:
        assert chunks == [tuple(row) for row in conn.execute("SELECT * FROM chunks ORDER BY id")]
    project = library.create_project("保留项目")
    library.set_membership(project["id"], document["document_id"], True)
    backup = Backups(db, root).create(root / "backups")
    restored = root / "restored"
    Backups.restore(backup, restored)
    restored_library = Library(Database(restored / "data/research.db"))
    assert restored_library.list_documents() == library.list_documents()
    assert restored_library.list_projects() == library.list_projects()


def test_doi_duplicate_is_only_a_review_candidate(workspace, tmp_path):
    root, db, library, imported, document = workspace
    PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/2020.emnlp-main.550.pdf", "two"
    )
    second = next(
        row for row in library.list_documents() if row["document_id"] != document["document_id"]
    )
    library.update_metadata(document["document_id"], metadata())
    saved = library.update_metadata(second["document_id"], metadata("另一份人工元数据"))
    assert saved["duplicate_candidates"] == [document["document_id"]]
    assert len(library.list_documents()) == 2
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM file_assets").fetchone()[0] == 2


def test_api_project_scope_and_unparsed_document_access(workspace):
    root, db, library, imported, document = workspace
    token = secrets.token_hex(32)
    headers = {"X-RAG-Session": token}
    with TestClient(create_app(token, root), base_url="http://127.0.0.1") as client:
        assert client.post("/v0/projects", json={"name": "denied"}).status_code == 401
        one = client.post("/v0/projects", headers=headers, json={"name": "项目一"}).json()
        two = client.post("/v0/projects", headers=headers, json={"name": "项目二"}).json()
        path = f"/v0/projects/{one['id']}/documents/{document['document_id']}"
        assert client.post(path, headers=headers, json={"linked": True}).status_code == 200
        result = client.get("/v0/documents", headers=headers, params={"project_id": two["id"]})
        assert result.json()["documents"] == []
        file = client.get(f"/v0/documents/{imported['doc_version_id']}/file", headers=headers)
        assert file.status_code == 200  # no ParseRun or synthetic SourceAnchor needed
        assert file.json()["file_sha256"] == imported["file_sha256"]
        assert "path" not in file.json() and "source_anchor_id" not in file.json()
        Parser(db, root).parse(imported["doc_version_id"], "parse")
        query = {
            "query": "BERT",
            "strategy": "fts_only",
            "project_id": two["id"],
            "authorized_doc_version_ids": [imported["doc_version_id"]],
            "k": 5,
        }
        assert client.post("/v0/search", headers=headers, json=query).status_code == 409
        query["project_id"] = one["id"]
        assert client.post("/v0/search", headers=headers, json=query).json()["results"]
        response = client.post(
            f"/v0/documents/{document['document_id']}/metadata",
            headers=headers,
            json=metadata(title=""),
        )
        assert response.status_code == 400


def test_hidden_or_corrupt_pdf_is_not_authorized_for_reader(workspace):
    root, db, library, imported, document = workspace
    with db.transaction() as conn:
        conn.execute("UPDATE document_versions SET visibility='hidden'")
    with pytest.raises(EngineError, match="NOT_FOUND"):
        library.file_record(imported["doc_version_id"], root)
    with db.transaction() as conn:
        conn.execute("UPDATE document_versions SET visibility='visible'")
    (root / "papers" / (imported["file_sha256"] + ".pdf")).write_bytes(b"corrupt")
    with pytest.raises(EngineError, match="OBJECT_CORRUPT"):
        library.file_record(imported["doc_version_id"], root)


def test_v3_upgrade_preserves_legacy_document_and_keeps_upgrade_backup(tmp_path):
    path = tmp_path / "data/research.db"
    path.parent.mkdir()
    scripts = sorted((ROOT / "engine/ragsystem/storage/migrations").glob("*.sql"))[:3]
    document_id = str(uuid4())
    with sqlite3.connect(path) as conn:
        for number, file in enumerate(scripts, 1):
            source = file.read_text()
            conn.executescript(source)
            conn.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (number, hashlib.sha256(source.encode()).hexdigest(), "legacy"),
            )
            conn.commit()
        conn.execute("INSERT INTO documents VALUES(?,?,?)", (document_id, "legacy title", "legacy"))
        conn.execute("PRAGMA user_version=3")
    upgraded = Database(path)
    with upgraded.connection() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("SELECT title FROM documents").fetchone()[0] == "legacy title"
    backups = list((path.parent / "migration-backups").glob("before-v3-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute("SELECT title FROM documents").fetchone()[0] == "legacy title"
    assert upgraded.integrity()["integrity_check"] == ["ok"]


def test_project_import_links_existing_pdf_in_same_transaction_and_recovers(workspace):
    root, db, library, imported, document = workspace
    project = library.create_project("导入目标")
    importer = PdfImporter(db, root)

    def interrupted(stage):
        if stage == "file_published":
            raise RuntimeError("simulate interruption")

    with pytest.raises(RuntimeError):
        importer.import_path_for_test(
            ROOT / "tests/fixtures/public/N19-1423.pdf",
            "project-import",
            project_id=project["id"],
            fault=interrupted,
        )
    assert library.list_documents(project["id"]) == []
    from ragsystem.jobs.repository import Jobs

    jobs = Jobs(db)
    job = jobs.find_key("import", "project-import")
    jobs.recover_expired(now=job["lease_until"] + 1)
    assert importer.recover_published_imports() == 1
    assert len(library.list_documents(project["id"])) == 1
    assert len(library.list_documents()) == 1
    assert jobs.get(job["id"])["status"] == "completed"


def test_project_names_normalized_and_invalid_membership_has_no_side_effect(workspace):
    root, db, library, imported, document = workspace
    project = library.create_project("Project A")
    with pytest.raises(EngineError, match="PROJECT_NAME_EXISTS"):
        library.create_project("Ｐｒｏｊｅｃｔ A")
    with pytest.raises(EngineError, match="NOT_FOUND"):
        library.set_membership(project["id"], str(uuid4()), True)
    with pytest.raises(EngineError, match="PROJECT_NOT_FOUND"):
        library.set_membership(str(uuid4()), document["document_id"], True)
    assert library.list_projects()[0]["document_count"] == 0
