import hashlib

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.storage.database import Database


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "本地 资料"
    return root, Database(root / "data" / "research.db")


def pdf_bytes(value=b"example"):
    # Synthetic bytes for storage/fault tests, never a scientific PDF sample.
    return b"%PDF-1.4\n" + value + b"\n%%EOF\n"


def test_import_is_immutable_and_deduplicated(store, tmp_path):
    root, db = store
    src = tmp_path / "原始.pdf"
    src.write_bytes(pdf_bytes())
    importer = PdfImporter(db, root)
    one = importer.import_path_for_test(src, "a")
    two = importer.import_path_for_test(src, "b")
    assert one["file_sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert one["doc_version_id"] == two["doc_version_id"]
    assert len(importer.list_documents()) == 1
    assert (root / "papers" / (one["file_sha256"] + ".pdf")).read_bytes() == src.read_bytes()
    assert db.integrity() == {"integrity_check": ["ok"], "foreign_key_check": []}


def test_same_filename_different_bytes_does_not_overwrite(store, tmp_path):
    root, db = store
    src = tmp_path / "same.pdf"
    src.write_bytes(pdf_bytes(b"one"))
    importer = PdfImporter(db, root)
    one = importer.import_path_for_test(src, "a")
    src.write_bytes(pdf_bytes(b"two"))
    two = importer.import_path_for_test(src, "b")
    assert one["file_sha256"] != two["file_sha256"]
    assert len(importer.list_documents()) == 2


def test_crash_after_publish_recovers_without_replacing_original(store, tmp_path):
    root, db = store
    src = tmp_path / "crash.pdf"
    src.write_bytes(pdf_bytes())
    importer = PdfImporter(db, root)

    def crash(stage):
        if stage == "file_published":
            raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError, match="injected crash"):
        importer.import_path_for_test(src, "recover", fault=crash)
    assert importer.list_documents() == []
    assert len(list((root / "papers").glob("*.pdf"))) == 1
    result = importer.import_path_for_test(src, "recover")
    assert result["file_sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert len(importer.list_documents()) == 1


def test_corrupt_existing_hash_target_is_never_overwritten(store, tmp_path):
    root, db = store
    src = tmp_path / "source.pdf"
    src.write_bytes(pdf_bytes())
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    (root / "papers").mkdir(parents=True)
    target = root / "papers" / (digest + ".pdf")
    target.write_bytes(b"corrupt existing object")
    with pytest.raises(EngineError, match="OBJECT_CORRUPT"):
        PdfImporter(db, root).import_path_for_test(src, "bad")
    assert target.read_bytes() == b"corrupt existing object"
    assert PdfImporter(db, root).list_documents() == []


def test_migration_rejects_future_schema_without_modifying_it(store):
    root, db = store
    with db.connection() as conn:
        conn.execute("PRAGMA user_version=999")
    with pytest.raises(EngineError, match="SCHEMA_TOO_NEW"):
        Database(root / "data" / "research.db")
    with db.connection() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 999
