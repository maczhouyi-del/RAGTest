from contextlib import contextmanager

from ragsystem.library.repository import Library
from ragsystem.storage.database import Database
from test_audit_task_contracts import versions


def test_document_list_has_bounded_bulk_queries_and_preserves_scope(tmp_path, monkeypatch):
    db = Database(tmp_path / "data/research.db")
    ids = versions(db, 50)
    original = db.connection
    statements = []
    @contextmanager
    def traced():
        with original() as conn:
            conn.set_trace_callback(statements.append)
            yield conn
    monkeypatch.setattr(db, "connection", traced)
    rows = Library(db).list_documents()
    count = sum(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    assert {row["doc_version_id"] for row in rows} == set(ids)
    assert all(row["metadata_extraction"]["status"] == "not_started" for row in rows)
    assert count <= 6, count
    statements.clear()
    one = Library(db).list_documents(doc_version_id=ids[0])
    assert len(one) == 1 and one[0]["doc_version_id"] == ids[0]
