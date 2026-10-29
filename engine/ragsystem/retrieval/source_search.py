import hashlib
from pathlib import Path

from ragsystem.domain.errors import EngineError
from ragsystem.retrieval.tokenizer import index_terms, quoted_phrases, search_terms, tokenize
from ragsystem.storage.database import Database


class Sources:
    def __init__(self, db: Database, root: Path):
        self.db, self.root = db, Path(root)

    @staticmethod
    def require_scope(conn, allowed_versions, project_id=None):
        placeholders = ",".join("?" for _ in allowed_versions)
        project_filter, project_params = "", []
        if project_id is not None:
            if conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
                raise EngineError("PROJECT_NOT_FOUND", status=404)
            project_filter = " AND EXISTS(SELECT 1 FROM project_documents pd WHERE pd.document_id=document_versions.document_id AND pd.project_id=? AND pd.linked=1)"
            project_params = [project_id]
        authorized = [
            row[0]
            for row in conn.execute(
                f"SELECT id FROM document_versions WHERE visibility='visible' AND id IN ({placeholders})"
                + project_filter,
                [*allowed_versions, *project_params],
            )
        ]
        if set(authorized) != set(allowed_versions):
            raise EngineError("SCOPE_NOT_AVAILABLE", status=409 if project_id is not None else 403)
        return authorized

    def search(
        self,
        query: str,
        allowed_versions: list[str],
        k: int,
        *,
        project_id=None,
        terms=False,
        phrase_priority=True,
    ):
        if (
            type(k) is not int
            or not 1 <= k <= 100
            or not query.strip()
            or len(query) > 20000
            or not 1 <= len(allowed_versions) <= 1000
        ):
            raise EngineError("INVALID_SEARCH")
        allowed_versions = list(dict.fromkeys(allowed_versions))
        placeholders = ",".join("?" for _ in allowed_versions)
        # A literal FTS phrase, not an SQL/FTS expression supplied by PDF text.
        phrase = '"' + query.replace('"', '""') + '"'
        table = "chunks_fts"
        phases = []
        if terms:
            self.ensure_terms()
            tokens = search_terms(query)[:100]
            phrase = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
            table = "chunks_terms_v2"
            if not phrase:
                raise EngineError("INVALID_SEARCH")
            explicit = quoted_phrases(query) if phrase_priority else []
            if explicit:
                phases.append(
                    (
                        "quoted_phrase",
                        " AND ".join(
                            '"' + " ".join(tokenize(value)).replace('"', '""') + '"'
                            for value in explicit
                        ),
                    )
                )
        phases.append(("or" if terms else "literal", phrase))
        with self.db.connection() as conn:
            # Scope validation and FTS read share one read snapshot, including
            # project membership. A concurrent edit cannot split their meaning.
            conn.execute("BEGIN")
            authorized = self.require_scope(conn, allowed_versions, project_id)
            rows, seen = [], set()
            for phase, expression in phases:
                candidates = conn.execute(
                    f"""SELECT c.*,bm25({table}) AS score FROM {table}
                JOIN chunks c ON c.id={table}.chunk_id
                JOIN document_versions v ON v.id=c.doc_version_id
                WHERE {table} MATCH ? AND c.visible=1 AND v.visibility='visible'
                    AND c.doc_version_id IN ({placeholders})
                ORDER BY score,c.id LIMIT ?""",
                    [expression, *authorized, k],
                ).fetchall()
                for phase_rank, row in enumerate(candidates, 1):
                    if row["id"] not in seen:
                        rows.append(
                            dict(row) | {"lexical_stage": phase, "lexical_stage_rank": phase_rank}
                        )
                        seen.add(row["id"])
                if len(rows) >= k:
                    break
            return [
                {
                    "doc_version_id": row["doc_version_id"],
                    "chunk_id": row["id"],
                    "source_anchor_id": row["id"],
                    "page_number": row["page_number"],
                    "preview": row["clean_text"],
                    "rank": rank + 1,
                    "lexical_rank": rank + 1,
                    "content_sha256": row["content_sha256"],
                    "bm25_score": row["score"],
                    "lexical_stage": row["lexical_stage"],
                    "lexical_stage_rank": row["lexical_stage_rank"],
                    "location_confidence": "unknown",
                }
                for rank, row in enumerate(rows[:k])
            ]

    def ensure_terms(self):
        while True:
            with self.db.transaction() as conn:
                rows = conn.execute("""SELECT c.id,c.clean_text FROM chunks c
                    LEFT JOIN terms_indexed_chunks_v2 t ON t.chunk_id=c.id
                    WHERE t.chunk_id IS NULL AND c.visible=1 LIMIT 200""").fetchall()
                for row in rows:
                    index_terms(conn, row["id"], row["clean_text"])
            if len(rows) < 200:
                break

    def anchor(self, anchor_id: str):
        with self.db.connection() as conn:
            row = conn.execute(
                """SELECT c.*,v.file_sha256,e.raw_text,e.page_rotation_degrees,e.quality_status
                FROM chunks c JOIN document_versions v ON v.id=c.doc_version_id
                JOIN elements e ON e.id=c.element_id AND e.parse_run_id=c.parse_run_id
                WHERE c.id=? AND c.visible=1 AND v.visibility='visible'""",
                (anchor_id,),
            ).fetchone()
        if row is None:
            raise EngineError("NOT_FOUND", status=404)
        if row["raw_text"][row["start_offset"] : row["end_offset"]] != row["clean_text"]:
            raise EngineError("SOURCE_ALIGNMENT_INVALID", status=409)
        path = self.root / "papers" / (row["file_sha256"] + ".pdf")
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 64 * 1024 * 1024
            or hashlib.sha256(path.read_bytes()).hexdigest() != row["file_sha256"]
        ):
            raise EngineError("OBJECT_CORRUPT", status=409)
        return {
            "schema_version": "0.1-draft",
            "source_anchor_id": row["id"],
            "doc_version_id": row["doc_version_id"],
            "file_sha256": row["file_sha256"],
            "parse_run_id": row["parse_run_id"],
            "element_id": row["element_id"],
            "page_number": row["page_number"],
            "location_level": "page_only",
            "coordinate_system": "page_normalized_top_left_unrotated_v1",
            "page_rotation_degrees": row["page_rotation_degrees"],
            "bbox_norm": None,
            "alignment_confidence": "unknown",
            "clean_text_offsets": {"start": row["start_offset"], "end": row["end_offset"]},
            "reason_if_degraded": "OCR_TEXT_UNREVIEWED_AND_VIEWER_COORDINATES_NOT_CALIBRATED"
            if row["quality_status"].startswith("ocr_")
            else "DOCLING_LAYOUT_TABLE_UNREVIEWED_AND_VIEWER_COORDINATES_NOT_CALIBRATED"
            if row["quality_status"].startswith("docling_")
            else "PDFIUM_VIEWER_COORDINATES_NOT_CALIBRATED",
            "source_text_sha256": hashlib.sha256(row["raw_text"].encode()).hexdigest(),
        }
