"""Immutable structure snapshots over current page pointers, including partial parses."""

import json
from collections import Counter
from uuid import uuid4

from ragsystem.chunking.structure import CONFIG, page_spans


def publish_structure(conn, version, run_id, revision):
    conn.execute(
        "INSERT INTO structure_publications VALUES(?,?,?,?)",
        (run_id, version, revision, json.dumps(CONFIG)),
    )
    stack = []
    edges = Counter()
    for row in conn.execute(
        "SELECT e.raw_text FROM published_pages p JOIN elements e ON e.id=p.element_id WHERE p.doc_version_id=?",
        (version,),
    ):
        lines = [line.strip() for line in row[0].splitlines() if line.strip()]
        edges.update(set(lines[:1] + lines[-1:]))
    repeated_edges = {line for line, count in edges.items() if count >= 3}

    # Recompute downstream context using existing page text, not PDF re-extraction.
    # Old chunks/links and old snapshots stay intact; the caller's transaction
    # publishes page pointers and structure together or rolls both back.
    pages = conn.execute(
        "SELECT e.* FROM published_pages p JOIN elements e ON e.id=p.element_id WHERE p.doc_version_id=? ORDER BY p.page_number",
        (version,),
    )
    for page in pages:
        stored = conn.execute(
            "SELECT blocks_json FROM parse_page_structure WHERE element_id=?", (page["id"],)
        ).fetchone()
        spans = list(page_spans(page["raw_text"], json.loads(stored[0]) if stored else None))
        paragraphs = []
        for span in spans:
            title = span.get("heading")
            if title and title["title"] in repeated_edges:
                title = None  # Repeated running headers/footers are not new sections.
            if title:
                while stack and stack[-1]["level"] >= title["level"]:
                    stack.pop()
                # Missing parent headings must never attach 3.1 to chapter 2.
                # Keep the detected level but leave the unknown ancestors absent.
                if title["number"]:
                    while stack and (
                        not stack[-1]["number"]
                        or not title["number"].startswith(stack[-1]["number"] + ".")
                    ):
                        stack.pop()
                section = {
                    **title,
                    "id": str(uuid4()),
                    "path": [s["title"] for s in stack] + [title["title"]],
                }
                conn.execute(
                    "INSERT INTO document_sections VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        section["id"],
                        run_id,
                        stack[-1]["id"] if stack else None,
                        title["title"],
                        title["level"],
                        json.dumps(section["path"], ensure_ascii=False),
                        page["page_number"],
                        page["page_number"],
                        title["method"],
                        title["confidence"],
                    ),
                )
                stack.append(section)
            for section in stack:
                conn.execute(
                    "UPDATE document_sections SET end_page=? WHERE id=?",
                    (page["page_number"], section["id"]),
                )
            sid = stack[-1]["id"] if stack else None
            pid = str(uuid4())
            reason = (
                "content_type_unclassified"
                if span["kind"] == "unknown"
                else None
                if sid
                else "section_unclassified"
            )
            kind = span["kind"]
            if (
                kind == "paragraph"
                and stack
                and stack[-1]["kind"] in {"abstract", "reference", "appendix"}
            ):
                kind = stack[-1]["kind"]
            conn.execute(
                "INSERT INTO document_paragraphs VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    pid,
                    run_id,
                    page["id"],
                    sid,
                    page["page_number"],
                    span["start"],
                    span["end"],
                    kind,
                    reason,
                ),
            )
            paragraphs.append((span["start"], span["end"], pid, sid, reason))
        # Merge-walk rather than scanning all paragraphs for every chunk.
        cursor = 0
        for chunk in conn.execute(
            "SELECT id,start_offset,end_offset FROM chunks WHERE element_id=? AND visible=1 ORDER BY start_offset",
            (page["id"],),
        ):
            while cursor < len(paragraphs) and paragraphs[cursor][1] <= chunk["start_offset"]:
                cursor += 1
            matched = paragraphs[cursor] if cursor < len(paragraphs) else None
            if (
                matched
                and matched[0] <= chunk["start_offset"]
                and chunk["end_offset"] <= matched[1]
            ):
                _, _, pid, sid, reason = matched
            else:
                pid, sid, reason = None, None, "legacy_or_unresolved_boundary"
            conn.execute(
                "INSERT INTO chunk_structure VALUES(?,?,?,?,?)",
                (run_id, chunk["id"], pid, sid, reason),
            )


def metadata(conn, chunk_id):
    row = conn.execute(
        """SELECT cs.publication_id,cs.paragraph_id,cs.section_id,cs.fallback_reason,
        s.section_title,s.section_level,s.section_path,s.parent_section_id,s.start_page,s.end_page,
        s.detection_method,s.detection_confidence,p.content_type
        FROM chunk_structure cs JOIN structure_publications pub ON pub.id=cs.publication_id
        JOIN parse_state state ON state.doc_version_id=pub.doc_version_id AND state.revision=pub.revision
        LEFT JOIN document_sections s ON s.id=cs.section_id
        LEFT JOIN document_paragraphs p ON p.id=cs.paragraph_id WHERE cs.chunk_id=?""",
        (chunk_id,),
    ).fetchone()
    if not row:
        return {"section_path": [], "fallback_reason": "legacy_unclassified"}
    value = dict(row)
    value["section_path"] = json.loads(value["section_path"] or "[]")
    return value
