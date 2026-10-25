"""Immutable table candidates and independent human review, tied to a ParseRun."""

import json
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.storage.database import utc_now


def persist_tables(conn, run_id, version_id, elements, tables):
    for ordinal, table in enumerate(tables):
        table_id = str(uuid4())
        element_id = elements.get(table["page_number"])
        conn.execute(
            "INSERT INTO parse_tables VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                table_id,
                run_id,
                version_id,
                element_id,
                table["page_number"],
                ordinal,
                table["source_ref"],
                json.dumps(table["source_pages"]),
                table["rows"],
                table["columns"],
                json.dumps(table["raw"], ensure_ascii=False),
            ),
        )
        for index, cell in enumerate(table["cells"]):
            if element_id is not None:
                text = conn.execute(
                    "SELECT raw_text FROM elements WHERE id=?", (element_id,)
                ).fetchone()[0]
                if (
                    cell["start"] is None
                    or cell["end"] is None
                    or text[cell["start"] : cell["end"]] != cell["text"]
                ):
                    raise EngineError("SOURCE_ALIGNMENT_INVALID")
            elif cell["start"] is not None or cell["end"] is not None:
                raise EngineError("SOURCE_ALIGNMENT_INVALID")
            conn.execute(
                "INSERT INTO table_cells VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    table_id,
                    index,
                    cell["row"],
                    cell["row_end"],
                    cell["column"],
                    cell["column_end"],
                    cell["text"],
                    int(cell["column_header"]),
                    int(cell["row_header"]),
                    cell["start"],
                    cell["end"],
                    json.dumps(cell["raw"], ensure_ascii=False),
                ),
            )


def matching_cells(conn, element_id, start, end):
    # Return candidates only when the quoted span intersects actual non-empty cell text.
    return [
        dict(row)
        for row in conn.execute(
            """SELECT t.id AS table_id, c.id AS cell_id,c.row_start,c.row_end,c.column_start,c.column_end,
           c.column_header,c.row_header FROM table_cells c JOIN parse_tables t ON t.id=c.table_id
           WHERE t.element_id=? AND c.end_offset>? AND c.start_offset<? AND LENGTH(c.text)>0
           ORDER BY t.ordinal,c.ordinal LIMIT 100""",
            (element_id, start, end),
        )
    ]


class Tables:
    def __init__(self, db):
        self.db = db

    def list(self, version_id, offset=0):
        with self.db.connection() as conn:
            conn.execute("BEGIN")
            if not conn.execute(
                "SELECT 1 FROM document_versions WHERE id=? AND visibility='visible'", (version_id,)
            ).fetchone():
                raise EngineError("NOT_FOUND", status=404)
            run = conn.execute(
                "SELECT last_parse_run_id FROM parse_state WHERE doc_version_id=?",
                (version_id,),
            ).fetchone()
            if run is None:
                return {"tables": [], "total": 0, "next_offset": None, "parse_run_id": None}
            total = conn.execute(
                "SELECT COUNT(*) FROM published_tables WHERE doc_version_id=?", (version_id,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT t.id,t.page_number,t.source_pages_json,t.row_count,t.column_count,t.ordinal FROM parse_tables t JOIN published_tables p ON p.table_id=t.id WHERE p.doc_version_id=? ORDER BY t.page_number,t.ordinal,t.id LIMIT 20 OFFSET ?",
                (version_id, offset),
            ).fetchall()
            return {
                "tables": [
                    {**dict(row), "source_pages": json.loads(row["source_pages_json"])}
                    for row in rows
                ],
                "total": total,
                "next_offset": offset + len(rows) if offset + len(rows) < total else None,
                "parse_run_id": run[0],
            }

    @staticmethod
    def require_current(conn, table_id):
        table = conn.execute(
            "SELECT t.* FROM parse_tables t JOIN document_versions v ON v.id=t.doc_version_id WHERE t.id=? AND v.visibility='visible'",
            (table_id,),
        ).fetchone()
        if table is None:
            raise EngineError("NOT_FOUND", status=404)
        current = conn.execute(
            "SELECT 1 FROM published_tables WHERE table_id=?", (table_id,)
        ).fetchone()
        if current is None:
            raise EngineError("SCOPE_STALE", status=409)
        return table

    def get(self, table_id, row_offset=0):
        with self.db.connection() as conn:
            conn.execute("BEGIN")
            table = self.require_current(conn, table_id)
            reviews = [
                dict(row)
                for row in conn.execute(
                    "SELECT revision,status,note,created_at FROM table_reviews WHERE table_id=? ORDER BY revision DESC LIMIT 20",
                    (table_id,),
                )
            ]
            cells = [
                dict(row)
                for row in conn.execute(
                    "SELECT id,row_start,row_end,column_start,column_end,text,column_header,row_header,start_offset,end_offset FROM table_cells WHERE table_id=? AND row_start<? AND row_end>? ORDER BY row_start,column_start,ordinal",
                    (table_id, row_offset + 10, row_offset),
                )
            ]
            return {
                key: table[key]
                for key in (
                    "id",
                    "doc_version_id",
                    "parse_run_id",
                    "page_number",
                    "row_count",
                    "column_count",
                    "source_ref",
                )
            } | {
                "source_pages": json.loads(table["source_pages_json"]),
                "cells": cells,
                "row_offset": row_offset,
                "next_row_offset": row_offset + 10
                if row_offset + 10 < table["row_count"]
                else None,
                "review": reviews[0]
                if reviews
                else {"revision": 0, "status": "unreviewed", "note": ""},
                "review_history": reviews,
                "location_level": "page_only",
                "coordinate_status": "uncalibrated",
                "scientific_comparability": "not_assessed",
                "candidate_only": True,
            }

    def review(self, table_id, body):
        with self.db.transaction() as conn:
            self.require_current(conn, table_id)
            revision = conn.execute(
                "SELECT COALESCE(MAX(revision),0) FROM table_reviews WHERE table_id=?", (table_id,)
            ).fetchone()[0]
            if revision != body.expected_revision:
                raise EngineError("REVIEW_CONFLICT", status=409)
            conn.execute(
                "INSERT INTO table_reviews VALUES(?,?,?,?,?,?)",
                (str(uuid4()), table_id, revision + 1, body.status, body.note, utc_now()),
            )
        return self.get(table_id)
