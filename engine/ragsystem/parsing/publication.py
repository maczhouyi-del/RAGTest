"""SQLite page publication pointers; immutable old content and review IDs survive."""

import json

from ragsystem.domain.errors import EngineError


def revision(conn, version):
    row = conn.execute("SELECT * FROM parse_state WHERE doc_version_id=?", (version,)).fetchone()
    return dict(row) if row else {"revision": 0, "page_count": 0, "unlocated_items": 0}


def validate_selection(selection):
    if selection is None:
        return None
    if (
        not isinstance(selection, list)
        or not 1 <= len(selection) <= 40
        or any(type(n) is not int or not 1 <= n <= 500 for n in selection)
        or len(selection) != len(set(selection))
    ):
        raise EngineError("INVALID_PARSE_PAGES")
    return sorted(selection)


def require_revision(conn, version, expected):
    if revision(conn, version)["revision"] != expected:
        raise EngineError("PARSE_PUBLICATION_CHANGED", status=409)


def begin_publish(conn, version, expected, selection, total_pages):
    require_revision(conn, version, expected)
    previous = revision(conn, version)
    if selection is not None and (
        previous["page_count"] != total_pages or max(selection) > total_pages
    ):
        raise EngineError("SOURCE_PAGE_INVALID")
    if selection is None:
        conn.execute("UPDATE chunks SET visible=0 WHERE doc_version_id=?", (version,))
        conn.execute("DELETE FROM published_pages WHERE doc_version_id=?", (version,))
        conn.execute("DELETE FROM published_tables WHERE doc_version_id=?", (version,))
    else:
        placeholders = ",".join("?" for _ in selection)
        conn.execute(
            f"UPDATE chunks SET visible=0 WHERE doc_version_id=? AND page_number IN ({placeholders})",
            (version, *selection),
        )
        conn.execute(
            f"DELETE FROM published_pages WHERE doc_version_id=? AND page_number IN ({placeholders})",
            (version, *selection),
        )
        # Multi-page or unlocated candidates cannot survive changing one of their
        # possible source pages; the immutable candidate/audit itself is retained.
        rows = conn.execute(
            "SELECT t.id,t.source_pages_json FROM parse_tables t JOIN published_tables p ON p.table_id=t.id WHERE p.doc_version_id=?",
            (version,),
        ).fetchall()
        for row in rows:
            numbers = json.loads(row["source_pages_json"])
            if not numbers or set(numbers).intersection(selection):
                conn.execute("DELETE FROM published_tables WHERE table_id=?", (row["id"],))


def finish_publish(conn, version, run_id, expected, total_pages, unresolved, unlocated, selection):
    # Unlocated objects have no defensible page ownership. A selective reparse
    # cannot establish that a previous document-wide gap has been repaired.
    unlocated = max(unlocated, revision(conn, version)["unlocated_items"] if selection else 0)
    count = conn.execute(
        "SELECT COUNT(*) FROM published_pages WHERE doc_version_id=?", (version,)
    ).fetchone()[0]
    if count != total_pages:
        raise EngineError("PARSE_PUBLICATION_INVALID")
    partial = (
        bool(unresolved or unlocated)
        or conn.execute(
            """SELECT 1 FROM published_pages p JOIN elements e ON e.id=p.element_id
        WHERE p.doc_version_id=? AND (e.error_code IS NOT NULL OR TRIM(e.raw_text)='' OR e.quality_status IN ('needs_ocr_or_review','ocr_low_confidence_unreviewed')) LIMIT 1""",
            (version,),
        ).fetchone()
        is not None
    )
    status = "partial" if partial else "ready"
    conn.execute(
        "INSERT INTO parse_state VALUES(?,?,?,?,?) ON CONFLICT(doc_version_id) DO UPDATE SET revision=excluded.revision,page_count=excluded.page_count,last_parse_run_id=excluded.last_parse_run_id,unlocated_items=excluded.unlocated_items",
        (version, expected + 1, total_pages, run_id, unlocated),
    )
    conn.execute("UPDATE document_versions SET parse_status=? WHERE id=?", (status, version))
    return status
