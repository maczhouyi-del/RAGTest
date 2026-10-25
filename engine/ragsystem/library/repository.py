import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ragsystem.domain.errors import EngineError
from ragsystem.storage.database import Database, utc_now

Name = Annotated[str, Field(min_length=1, max_length=200)]


class MetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=1000)
    authors: list[Name] = Field(default_factory=list, max_length=100)
    year: int | None = Field(default=None, ge=1000, le=2999)
    doi: str | None = Field(default=None, max_length=300)
    venue: str = Field(default="", max_length=500)
    tags: list[Name] = Field(default_factory=list, max_length=30)
    abstract: str = Field(default="", max_length=8000)
    field_actions: dict[str, str] | None = Field(default=None, max_length=6)
    doc_version_id: str | None = Field(default=None, max_length=100)

    @field_validator("title", "venue")
    @classmethod
    def clean_text(cls, value, info):
        value = value.strip()
        if info.field_name == "title" and not value:
            raise ValueError("title required")
        if any(ord(char) < 32 and char not in "\t\n" for char in value):
            raise ValueError("control characters")
        return value

    @field_validator("authors", "tags")
    @classmethod
    def clean_labels(cls, values, info):
        values = [value.strip() for value in values]
        if any(not value or any(ord(char) < 32 for char in value) for value in values):
            raise ValueError("label invalid")
        return list(dict.fromkeys(values)) if info.field_name == "tags" else values

    @field_validator("doi")
    @classmethod
    def normalize_doi(cls, value):
        if value is None or not value.strip():
            return None
        value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I)
        if not re.fullmatch(r"10\.\d{4,9}/[^\s\x00-\x1f]+", value):
            raise ValueError("DOI format invalid")
        return value.lower()


class Library:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def require_project(conn, project_id):
        if conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
            raise EngineError("PROJECT_NOT_FOUND", status=404)

    @staticmethod
    def require_document(conn, document_id):
        if (
            conn.execute(
                "SELECT 1 FROM document_versions WHERE document_id=? AND visibility='visible'",
                (document_id,),
            ).fetchone()
            is None
        ):
            raise EngineError("NOT_FOUND", status=404)

    def create_project(self, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise EngineError("INVALID_PROJECT")
        name = name.strip()
        if any(ord(char) < 32 for char in name):
            raise EngineError("INVALID_PROJECT")
        project_id, stamp = str(uuid4()), utc_now()
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO projects VALUES(?,?,?,?)",
                    (project_id, name, unicodedata.normalize("NFKC", name).casefold(), stamp),
                )
        except sqlite3.IntegrityError as exc:
            raise EngineError("PROJECT_NAME_EXISTS", status=409) from exc
        return {"id": project_id, "name": name, "created_at": stamp, "document_count": 0}

    def list_projects(self):
        with self.db.connection() as conn:
            return [
                dict(row)
                for row in conn.execute("""SELECT p.id,p.name,p.created_at,
                (SELECT COUNT(*) FROM project_documents pd WHERE pd.project_id=p.id
                 AND pd.linked=1 AND EXISTS(SELECT 1 FROM document_versions v
                 WHERE v.document_id=pd.document_id AND v.visibility='visible')) AS document_count
                FROM projects p ORDER BY p.created_at,p.id""")
            ]

    def set_membership(self, project_id, document_id, linked):
        if not isinstance(linked, bool):
            raise EngineError("INVALID_MEMBERSHIP")
        with self.db.transaction() as conn:
            self.require_project(conn, project_id)
            self.require_document(conn, document_id)
            conn.execute(
                """INSERT INTO project_documents VALUES(?,?,?,?)
                ON CONFLICT(project_id,document_id) DO UPDATE SET linked=excluded.linked,
                updated_at=excluded.updated_at WHERE project_documents.linked!=excluded.linked""",
                (project_id, document_id, int(linked), utc_now()),
            )
        return {"project_id": project_id, "document_id": document_id, "linked": linked}

    def list_documents(self, project_id=None):
        with self.db.connection() as conn:
            if project_id is not None:
                self.require_project(conn, project_id)
            query = """SELECT d.id AS document_id,d.title,v.id AS doc_version_id,v.file_sha256,
                v.parse_status,v.created_at,f.size_bytes,m.authors_json,m.publication_year AS year,
                m.doi,m.venue,m.tags_json,COALESCE(m.revision,0) AS metadata_revision,
                m.origin AS metadata_origin,m.abstract,m.field_origins_json
                FROM documents d JOIN document_versions v ON v.document_id=d.id
                JOIN file_assets f ON f.sha256=v.file_sha256
                LEFT JOIN document_metadata m ON m.document_id=d.id WHERE v.visibility='visible'"""
            params = ()
            if project_id is not None:
                query += " AND EXISTS(SELECT 1 FROM project_documents pd WHERE pd.document_id=d.id AND pd.project_id=? AND pd.linked=1)"
                params = (project_id,)
            rows = [
                dict(row)
                for row in conn.execute(query + " ORDER BY v.created_at DESC,v.id", params)
            ]
            memberships = {}
            for row in conn.execute(
                "SELECT document_id,project_id FROM project_documents WHERE linked=1 ORDER BY project_id"
            ):
                memberships.setdefault(row["document_id"], []).append(row["project_id"])
            for row in rows:
                row["authors"] = json.loads(row.pop("authors_json") or "[]")
                row["tags"] = json.loads(row.pop("tags_json") or "[]")
                row["venue"] = row["venue"] or ""
                row["abstract"] = row["abstract"] or ""
                origins = json.loads(row.pop("field_origins_json") or "{}")
                from ragsystem.library.metadata import VERSION

                candidates = {}
                for candidate in conn.execute(
                    "SELECT * FROM metadata_candidates WHERE document_id=? AND doc_version_id=? AND extractor_version=? ORDER BY created_at,id",
                    (row["document_id"], row["doc_version_id"], VERSION),
                ):
                    value = dict(candidate)
                    value["value"] = json.loads(value.pop("candidate_value"))
                    candidates[value["field_name"]] = value
                for field, candidate in candidates.items():
                    if origins.get(field) not in {"manual", "confirmed"}:
                        row[field] = candidate["value"]
                        origins[field] = "automatic"
                row["metadata_origins"] = origins
                row["metadata_candidates"] = candidates
                row["metadata_pending"] = any(
                    origins.get(field) == "automatic" and value["review_status"] == "unreviewed"
                    for field, value in candidates.items()
                )
                extraction = conn.execute(
                    "SELECT status,error_code FROM jobs WHERE type='verify' AND idempotency_key=?",
                    (VERSION + ":" + row["doc_version_id"],),
                ).fetchone()
                row["metadata_extraction"] = (
                    dict(extraction)
                    if extraction
                    else {"status": "not_started", "error_code": None}
                )
                row["metadata_origin"] = (
                    "manual"
                    if any(v in {"manual", "confirmed"} for v in origins.values())
                    else "automatic"
                    if candidates
                    else None
                )
                row["project_ids"] = memberships.get(row["document_id"], [])
                row["duplicate_candidates"] = (
                    [
                        other[0]
                        for other in conn.execute(
                            """SELECT m.document_id FROM document_metadata m WHERE m.doi=? AND m.document_id!=?
                       AND EXISTS(SELECT 1 FROM document_versions v WHERE v.document_id=m.document_id
                       AND v.visibility='visible') ORDER BY m.document_id""",
                            (row["doi"], row["document_id"]),
                        )
                    ]
                    if row["doi"]
                    else []
                )
            return rows

    def update_metadata(self, document_id, value):
        try:
            body = (
                value if isinstance(value, MetadataUpdate) else MetadataUpdate.model_validate(value)
            )
        except ValidationError as exc:
            raise EngineError("INVALID_METADATA") from exc
        current_values = next(
            (
                row
                for row in self.list_documents()
                if row["document_id"] == document_id
                and (body.doc_version_id is None or row["doc_version_id"] == body.doc_version_id)
            ),
            None,
        )
        if current_values is None:
            raise EngineError("NOT_FOUND", status=404)
        from ragsystem.library.metadata import FIELDS

        origins = dict(current_values["metadata_origins"])
        requested = body.model_dump()
        actions = (
            body.field_actions
            if body.field_actions is not None
            else {field: "manual" for field in FIELDS}
        )
        if any(field not in FIELDS for field in actions):
            raise EngineError("INVALID_METADATA")
        if body.field_actions is None and "abstract" not in body.model_fields_set:
            actions["abstract"] = "keep"
        accepted = []
        for field in FIELDS:
            action = actions.get(field, "keep")
            if action == "keep":
                requested[field] = current_values[field]
            elif action in {"manual", "confirm"}:
                if action == "confirm":
                    requested[field] = current_values[field]
                origins[field] = "confirmed" if action == "confirm" else "manual"
            else:
                candidate = current_values["metadata_candidates"].get(field)
                if not candidate or candidate["id"] != action:
                    raise EngineError("METADATA_CANDIDATE_CHANGED", status=409)
                requested[field] = candidate["value"]
                origins[field] = "automatic"
                accepted.append(candidate["id"])
        body = MetadataUpdate.model_validate(requested)
        with self.db.transaction() as conn:
            self.require_document(conn, document_id)
            current = conn.execute(
                "SELECT revision FROM document_metadata WHERE document_id=?", (document_id,)
            ).fetchone()
            revision = current[0] if current else 0
            if revision != body.expected_revision:
                raise EngineError("METADATA_CONFLICT", status=409)
            conn.execute("UPDATE documents SET title=? WHERE id=?", (body.title, document_id))
            conn.execute(
                """INSERT INTO document_metadata(document_id,authors_json,publication_year,doi,venue,tags_json,revision,origin,updated_at,abstract,field_origins_json) VALUES(?,?,?,?,?,?,?,'manual',?,?,?)
                ON CONFLICT(document_id) DO UPDATE SET authors_json=excluded.authors_json,
                publication_year=excluded.publication_year,doi=excluded.doi,venue=excluded.venue,
                tags_json=excluded.tags_json,revision=excluded.revision,updated_at=excluded.updated_at,abstract=excluded.abstract,field_origins_json=excluded.field_origins_json""",
                (
                    document_id,
                    json.dumps(body.authors, ensure_ascii=False),
                    body.year,
                    body.doi,
                    body.venue,
                    json.dumps(body.tags, ensure_ascii=False),
                    revision + 1,
                    utc_now(),
                    body.abstract,
                    json.dumps(origins),
                ),
            )
            for candidate_id in accepted:
                conn.execute(
                    "UPDATE metadata_candidates SET review_status='accepted' WHERE id=?",
                    (candidate_id,),
                )
        return next(row for row in self.list_documents() if row["document_id"] == document_id)

    def file_record(self, version_id, root: Path):
        with self.db.connection() as conn:
            row = conn.execute(
                """SELECT v.id AS doc_version_id,v.file_sha256,d.title,f.size_bytes
                FROM document_versions v JOIN documents d ON d.id=v.document_id
                JOIN file_assets f ON f.sha256=v.file_sha256
                WHERE v.id=? AND (v.visibility='visible' OR EXISTS(SELECT 1 FROM document_lifecycle l WHERE l.document_id=v.document_id AND l.state IN ('archived','retracted')))""",
                (version_id,),
            ).fetchone()
        if row is None:
            raise EngineError("NOT_FOUND", status=404)
        path = root / "papers" / (row["file_sha256"] + ".pdf")
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != row["size_bytes"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != row["file_sha256"]
        ):
            raise EngineError("OBJECT_CORRUPT", status=409)
        return dict(row)

    def _ocr_configured(self):
        with self.db.connection() as conn:
            return conn.execute("SELECT 1 FROM app_settings WHERE key='ocr'").fetchone() is not None

    def parse_diagnostics(self, version_id):
        with self.db.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM document_versions WHERE id=? AND visibility='visible'", (version_id,)
            ).fetchone():
                raise EngineError("NOT_FOUND", status=404)
            runs = [
                dict(row)
                for row in conn.execute(
                    "SELECT id,status,page_count,error_code,created_at,finished_at FROM parse_runs WHERE doc_version_id=? ORDER BY created_at DESC LIMIT 10",
                    (version_id,),
                )
            ]
            for run in runs:
                run["parser_configuration"] = None
                for event in conn.execute(
                    "SELECT details_json FROM events WHERE kind='parser_fingerprint' ORDER BY id DESC"
                ):
                    details = json.loads(event[0])
                    if details.get("parse_run_id") == run["id"]:
                        run["parser_configuration"] = details["configuration"]
                        break
            pages = [
                dict(row)
                for row in conn.execute(
                    "SELECT p.page_number,e.parse_run_id,e.quality_status AS quality,e.error_code,LENGTH(e.raw_text) AS text_chars FROM published_pages p JOIN elements e ON e.id=p.element_id WHERE p.doc_version_id=? ORDER BY p.page_number",
                    (version_id,),
                )
            ]
            state = conn.execute(
                "SELECT revision,page_count,unlocated_items FROM parse_state WHERE doc_version_id=?",
                (version_id,),
            ).fetchone()
            for run in runs:
                run["attempts"] = [
                    dict(row)
                    for row in conn.execute(
                        "SELECT id,method,status,page_numbers_json,error_code,created_at,finished_at FROM parse_attempts WHERE parse_run_id=? ORDER BY created_at,id",
                        (run["id"],),
                    )
                ]
                for event in conn.execute(
                    "SELECT details_json FROM events WHERE kind='parser_result' ORDER BY id DESC"
                ):
                    details = json.loads(event[0])
                    if details.get("parse_run_id") == run["id"]:
                        run["routing"] = details.get("routing", [])
                        metadata = {row["page_number"]: row for row in details["pages"]}
                        for page in pages:
                            if page["parse_run_id"] == run["id"]:
                                page.update(metadata.get(page["page_number"], {}))
                        break
        return {
            "runs": runs,
            "publication_revision": state["revision"] if state else 0,
            "unlocated_items": state["unlocated_items"] if state else 0,
            "pages": pages,
            "needs_ocr_pages": [
                page["page_number"]
                for page in pages
                if page["quality"]
                in {"needs_ocr_or_review", "ocr_low_confidence_unreviewed", "failed"}
            ],
            "ocr_configured": self._ocr_configured(),
            "docling_configured": self._docling_configured(),
        }

    def _docling_configured(self):
        with self.db.connection() as conn:
            return (
                conn.execute("SELECT 1 FROM app_settings WHERE key='docling'").fetchone()
                is not None
            )
