import json

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import Database


def make_store(tmp_path):
    root = tmp_path / "live"
    db = Database(root / "data/research.db")
    source = tmp_path / "storage-only.pdf"
    source.write_bytes(b"%PDF-1.4\nsynthetic persistence test only\n%%EOF")
    PdfImporter(db, root).import_path_for_test(source, "one")
    return root, db


def test_snapshot_restore_preserves_hash_truth_and_job(tmp_path):
    root, db = make_store(tmp_path)
    manager = Backups(db, root)
    snapshot = manager.create(tmp_path / "备份 空格")
    target = tmp_path / "恢复 空格"
    manager.restore(snapshot, target)
    restored = Database(target / "data/research.db")
    assert restored.integrity() == {"integrity_check": ["ok"], "foreign_key_check": []}
    assert PdfImporter(restored, target).list_documents() == PdfImporter(db, root).list_documents()
    with restored.connection() as conn:
        assert conn.execute("SELECT status FROM jobs").fetchone()[0] == "completed"
    with pytest.raises(EngineError, match="RESTORE_TARGET_EXISTS"):
        manager.restore(snapshot, target)


def test_corrupt_pdf_prevents_restore_before_creating_target(tmp_path):
    root, db = make_store(tmp_path)
    manager = Backups(db, root)
    snapshot = manager.create(tmp_path / "snapshots")
    pdf = next((snapshot / "papers").glob("*.pdf"))
    pdf.write_bytes(b"tampered")
    target = tmp_path / "restored"
    with pytest.raises(EngineError, match="BACKUP_HASH_MISMATCH"):
        manager.restore(snapshot, target)
    assert not target.exists()


def test_untrusted_manifest_cannot_escape_restore_root(tmp_path):
    root, db = make_store(tmp_path)
    manager = Backups(db, root)
    snapshot = manager.create(tmp_path / "snapshots")
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][0]["path"] = "../../outside.pdf"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(EngineError, match="BACKUP_MANIFEST_INVALID"):
        manager.restore(snapshot, tmp_path / "target")
    assert not (tmp_path / "outside.pdf").exists()
