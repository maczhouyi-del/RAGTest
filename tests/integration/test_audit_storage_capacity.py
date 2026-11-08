import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.jobs.repository import Jobs
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import Database


def store(tmp_path):
    root = tmp_path / "workspace"
    db = Database(root / "data/research.db")
    source = tmp_path / "synthetic-storage.pdf"
    source.write_bytes(b"%PDF-1.4\nstorage fixture only\n%%EOF")
    return root, db, source


def test_ten_duplicate_imports_retire_only_successful_owned_staging(tmp_path):
    root, db, source = store(tmp_path)
    importer = PdfImporter(db, root)
    unrelated = root / "staging/unknown-user-file.part"
    unrelated.write_bytes(b"preserve unknown owner")
    refs = [importer.import_path_for_test(source, "0")]
    initial_blocks = sum(p.stat().st_blocks for directory in (root/"staging", root/"papers") for p in directory.iterdir())
    refs += [importer.import_path_for_test(source, str(i)) for i in range(1, 10)]
    assert len({row["doc_version_id"] for row in refs}) == 1
    assert list((root / "staging").iterdir()) == [unrelated]
    assert len(list((root / "papers").iterdir())) == 1
    assert unrelated.read_bytes() == b"preserve unknown owner"
    assert sum(p.stat().st_blocks for directory in (root/"staging", root/"papers") for p in directory.iterdir()) == initial_blocks


def test_import_staging_kept_after_publication_crash_and_cleanup_failure_audited(tmp_path, monkeypatch):
    root, db, source = store(tmp_path)
    importer = PdfImporter(db, root)
    def crash(stage):
        if stage == "file_published":
            raise RuntimeError("injected crash")
    with pytest.raises(RuntimeError):
        importer.import_path_for_test(source, "crashed", fault=crash)
    before = {p.name:p.read_bytes() for p in (root / "staging").iterdir()}
    from pathlib import Path
    original = Path.unlink
    def deny(self, *args, **kwargs):
        if self.suffix == ".part":
            raise PermissionError("injected cleanup denial")
        return original(self, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", deny)
        importer.import_path_for_test(source, "success")
    for name, content in before.items():
        assert (root / "staging" / name).read_bytes() == content
    job = Jobs(db).find_key("import", "success")
    assert job["status"] == "completed"
    with db.connection() as conn:
        assert conn.execute("SELECT 1 FROM events WHERE job_id=? AND kind='staging_cleanup_pending'", (job["id"],)).fetchone()


@pytest.mark.parametrize("limit", ["database", "total", "free"])
def test_backup_preflight_rejects_before_copy(tmp_path, monkeypatch, limit):
    import ragsystem.storage.backup as module
    root, db, source = store(tmp_path)
    PdfImporter(db, root).import_path_for_test(source, "one")
    if limit == "database":
        monkeypatch.setattr(module, "MAX_DATABASE_BYTES", 1, raising=False)
    elif limit == "total":
        monkeypatch.setattr(module, "MAX_BACKUP_BYTES", 1, raising=False)
    else:
        usage = module.shutil.disk_usage(tmp_path)
        monkeypatch.setattr(module.shutil, "disk_usage", lambda path: type(usage)(usage.total, usage.used, 1))
    def forbidden(*args, **kwargs):
        raise AssertionError("must reject before copying SQLite or PDF")
    monkeypatch.setattr(Backups, "_create", forbidden)
    with pytest.raises(EngineError, match="BACKUP_CAPACITY_LIMIT|BACKUP_SPACE_INSUFFICIENT"):
        Backups(db, root).create(tmp_path / "copies")
