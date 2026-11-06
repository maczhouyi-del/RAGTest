import json
from pathlib import Path

from ragsystem.chunking.publication import metadata
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import Database


def test_real_pdf_structure_partial_publication_and_backup(tmp_path):
    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    source = Path(__file__).resolve().parents[2] / "tests/fixtures/public/N19-1423.pdf"
    version = PdfImporter(db, root).import_path_for_test(source, "bert")["doc_version_id"]
    parser = Parser(db, root)
    parser.parse(version, "full")
    with db.connection() as conn:
        original = [dict(r) for r in conn.execute("SELECT * FROM chunks WHERE visible=1")]
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT id,start_offset,end_offset FROM chunks WHERE element_id=? AND visible=1 ORDER BY start_offset",
            (original[0]["element_id"],),
        ).fetchall()
        assert any("chunks_by_element_offsets" in row["detail"] for row in plan)
        assert conn.execute("SELECT count(*) FROM document_sections").fetchone()[0] > 5
        assert any(metadata(conn, c["id"])["section_path"] for c in original)
        assert conn.execute("SELECT count(*) FROM chunk_structure").fetchone()[0] == len(original)
        assert json.loads(
            conn.execute(
                "SELECT section_path FROM document_sections WHERE section_title='3.1 Pre-training BERT'"
            ).fetchone()[0]
        ) == ["3 BERT", "3.1 Pre-training BERT"]
        assert (
            conn.execute(
                "SELECT count(*) FROM (SELECT paragraph_id FROM chunk_structure GROUP BY paragraph_id HAVING count(*)>1)"
            ).fetchone()[0]
            > 0
        )
    for chunk in original:
        Sources(db, root).anchor(chunk["id"])
        assert len(chunk["clean_text"]) <= 400
    parser.parse(version, "partial", page_numbers=[2])
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) FROM structure_publications").fetchone()[0] == 2
        for c in original:
            if c["page_number"] != 2:
                assert (
                    conn.execute("SELECT visible FROM chunks WHERE id=?", (c["id"],)).fetchone()[0]
                    == 1
                )
                assert metadata(conn, c["id"])["publication_id"] != c["parse_run_id"]
        assert (
            conn.execute(
                "SELECT count(*) FROM document_paragraphs WHERE publication_id=(SELECT last_parse_run_id FROM parse_state WHERE doc_version_id=?)",
                (version,),
            ).fetchone()[0]
            > 0
        )
    backup = Backups(db, root).create(tmp_path / "backup")
    Backups.restore(backup, tmp_path / "restored")
    restored = Database(tmp_path / "restored/data/research.db")
    assert restored.integrity()["foreign_key_check"] == []
    with restored.connection() as conn:
        assert conn.execute("SELECT count(*) FROM structure_publications").fetchone()[0] == 2
        for row in conn.execute("SELECT section_path FROM document_sections"):
            assert isinstance(json.loads(row[0]), list)


def test_downstream_context_changes_atomically_without_rechunking(tmp_path, monkeypatch):
    import pytest
    from ragsystem.domain.errors import EngineError
    from ragsystem.indexing.embeddings import Embeddings
    from ragsystem.parsing import pipeline

    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    source = Path(__file__).resolve().parents[2] / "tests/fixtures/public/N19-1423.pdf"
    version = PdfImporter(db, root).import_path_for_test(source, "bert")["doc_version_id"]
    changed = False

    def worker(request, **kwargs):
        numbers = request.get("page_numbers") or list(range(1, 17))
        return {
            "document_page_count": 16,
            "pages": [
                {
                    "page_number": n,
                    "text": (
                        "1 Introduction\n"
                        if n == 1
                        else "2 Methods\n"
                        if n == 2 and changed
                        else ""
                    )
                    + "Paragraph for this page.",
                    "error_code": None,
                    "rotation": 0,
                }
                for n in numbers
            ],
        }

    monkeypatch.setattr(pipeline, "run_worker", worker)
    parser = Parser(db, root)
    parser.parse(version, "base")
    with db.connection() as conn:
        third = conn.execute("SELECT id FROM chunks WHERE page_number=3 AND visible=1").fetchone()[
            0
        ]
        assert metadata(conn, third)["section_path"] == ["1 Introduction"]
        digest = conn.execute("SELECT content_sha256 FROM chunks WHERE id=?", (third,)).fetchone()[
            0
        ]
    cache = Embeddings(db)
    space = cache.space(
        {
            "model": "SYNTHETIC_NOT_A_MODEL",
            "revision": "test",
            "weight_sha256": "a" * 64,
            "tokenizer_sha256": "b" * 64,
            "preprocessing": {},
            "dimension": 3,
            "metric": "cosine",
            "normalization": "none",
        }
    )
    embedding_id = cache.persist(space, digest, [1, 0, 0])
    cache.link(third, embedding_id)
    changed = True
    parser.parse(version, "partial", page_numbers=[2])
    with db.connection() as conn:
        assert metadata(conn, third)["section_path"] == ["2 Methods"]
        assert conn.execute("SELECT count(*) FROM structure_publications").fetchone()[0] == 2
        assert (
            conn.execute(
                "SELECT embedding_id FROM chunk_embedding_links WHERE chunk_id=?",
                (third,),
            ).fetchone()[0]
            == embedding_id
        )
    assert cache.get(space, digest)["id"] == embedding_id

    def fail(*args):
        raise EngineError("INJECTED_STRUCTURE_FAILURE")

    monkeypatch.setattr(pipeline, "publish_structure", fail)
    with pytest.raises(EngineError, match="INJECTED_STRUCTURE_FAILURE"):
        parser.parse(version, "failure", page_numbers=[2])
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) FROM structure_publications").fetchone()[0] == 2
        assert metadata(conn, third)["section_path"] == ["2 Methods"]


def test_v20_upgrade_preserves_old_rows_and_old_backup_restores(tmp_path):
    import hashlib
    import sqlite3

    from ragsystem.storage.database import utc_now

    path = tmp_path / "legacy.db"
    migrations = Path(__file__).resolve().parents[2] / "engine/ragsystem/storage/migrations"
    with sqlite3.connect(path) as conn:
        for file in sorted(migrations.glob("*.sql")):
            n = int(file.name.split("_")[0])
            if n > 20:
                break
            script = file.read_text()
            conn.executescript(script)
            conn.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (n, hashlib.sha256(script.encode()).hexdigest(), utc_now()),
            )
        conn.execute("PRAGMA user_version=20")
        conn.execute("INSERT INTO app_settings VALUES('sentinel','{}',?)", (utc_now(),))
    # A real v20 SQLite snapshot and hash-checked legacy manifest, before migration.
    snapshot = tmp_path / "v20-backup"
    (snapshot / "data").mkdir(parents=True)
    old_bytes = path.read_bytes()
    (snapshot / "data/research.db").write_bytes(old_bytes)
    (snapshot / "manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": "0.1.0",
                "schema_version": 20,
                "status": "complete",
                "files": [
                    {
                        "path": "data/research.db",
                        "sha256": hashlib.sha256(old_bytes).hexdigest(),
                    }
                ],
            }
        )
    )
    assert Backups.inspect(snapshot)["manifest"]["schema_version"] == 20
    Backups.restore(snapshot, tmp_path / "v20-restored")
    restored = Database(tmp_path / "v20-restored/data/research.db")
    assert restored.schema_version() == 21
    assert restored.integrity()["foreign_key_check"] == []
    with restored.connection() as conn:
        assert (
            conn.execute("SELECT value_json FROM app_settings WHERE key='sentinel'").fetchone()[0]
            == "{}"
        )
    db = Database(path)
    assert db.schema_version() == 21
    with db.connection() as conn:
        assert (
            conn.execute("SELECT value_json FROM app_settings WHERE key='sentinel'").fetchone()[0]
            == "{}"
        )
        assert conn.execute("SELECT count(*) FROM document_sections").fetchone()[0] == 0
    assert list((tmp_path / "migration-backups").glob("before-v20-*.db"))


def test_missing_parent_and_running_headers_do_not_fabricate_hierarchy(tmp_path, monkeypatch):
    from ragsystem.parsing import pipeline

    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    source = Path(__file__).resolve().parents[2] / "tests/fixtures/public/N19-1423.pdf"
    version = PdfImporter(db, root).import_path_for_test(source, "bert")["doc_version_id"]

    def worker(request, **kwargs):
        return {
            "document_page_count": 16,
            "pages": [
                {
                    "page_number": n,
                    "text": "Introduction\n"
                    + (
                        "2 Related Work\n"
                        if n == 1
                        else "3.1 Model Architecture\n"
                        if n == 2
                        else ""
                    )
                    + "Body for page "
                    + str(n),
                    "error_code": None,
                    "rotation": 0,
                }
                for n in range(1, 17)
            ],
        }

    monkeypatch.setattr(pipeline, "run_worker", worker)
    Parser(db, root).parse(version, "base")
    with db.connection() as conn:
        assert not conn.execute(
            "SELECT 1 FROM document_sections WHERE section_title='Introduction'"
        ).fetchall()
        section = conn.execute(
            "SELECT * FROM document_sections WHERE section_title='3.1 Model Architecture'"
        ).fetchone()
        assert section["parent_section_id"] is None
        assert json.loads(section["section_path"]) == ["3.1 Model Architecture"]
        assert section["section_level"] == 2 and section["end_page"] == 16
