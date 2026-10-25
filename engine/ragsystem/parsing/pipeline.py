import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from ragsystem.chunking.mapping import chunk_page
from ragsystem.domain.errors import EngineError
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.docling import POLICY as DOCLING_POLICY
from ragsystem.parsing.docling import DoclingService
from ragsystem.parsing.ocr import POLICY, OcrService
from ragsystem.parsing.process import run_worker
from ragsystem.parsing.publication import (
    begin_publish,
    finish_publish,
    require_revision,
    revision,
    validate_selection,
)
from ragsystem.parsing.routing import POLICY as ROUTE_POLICY
from ragsystem.parsing.routing import accept, choose
from ragsystem.parsing.tables import persist_tables
from ragsystem.retrieval.tokenizer import index_terms
from ragsystem.storage.database import Database, utc_now

PARSER_CONFIG = {
    "pipeline": "pdfium-page-chunks-v2",
    "max_pages": 500,
    "max_page_chars": 50000,
    "chunk_max_chars": 400,
    "chunk_overlap_chars": 80,
    "chunk_boundaries": "page-sentence-newline-v2",
    "offset_unit": "unicode_codepoint",
}


class Parser:
    def __init__(self, db: Database, root: Path):
        self.db, self.root, self.jobs = db, Path(root), Jobs(db)

    def parse(
        self,
        doc_version_id: str,
        key: str,
        *,
        queue_only: bool = False,
        use_ocr: bool = False,
        use_docling: bool = False,
        auto_enhance: bool = False,
        page_numbers: list[int] | None = None,
        parent_check=None,
    ):
        if sum((use_ocr, use_docling, auto_enhance)) > 1:
            raise EngineError("PARSER_OPTIONS_CONFLICT")
        selection = validate_selection(page_numbers)
        existing = self.jobs.find_key("parse_page", key)
        options = {
            "use_ocr": use_ocr,
            "use_docling": use_docling,
            "auto_enhance": auto_enhance,
            "page_numbers": selection,
        }
        old_payload = json.loads(existing["payload_json"]) if existing else {}
        if existing:
            if old_payload["doc_version_id"] != doc_version_id or any(
                old_payload.get(name, False if name != "page_numbers" else None) != value
                for name, value in options.items()
            ):
                raise EngineError("IDEMPOTENCY_CONFLICT", status=409)
            if existing["status"] == "completed":
                return existing
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM document_versions WHERE id=? AND visibility='visible'",
                (doc_version_id,),
            ).fetchone()
            state = revision(conn, doc_version_id)
            expected = old_payload.get("base_revision", state["revision"])
            require_revision(conn, doc_version_id, expected)
            if selection is not None:
                if not state["page_count"]:
                    raise EngineError("PARTIAL_PARSE_NEEDS_BASE")
                if max(selection) > state["page_count"]:
                    raise EngineError("SOURCE_PAGE_INVALID")
        if row is None:
            raise EngineError("NOT_FOUND", status=404)
        path = self.root / "papers" / (row["file_sha256"] + ".pdf")
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != row["file_sha256"]
        ):
            raise EngineError("OBJECT_CORRUPT", status=409)
        import pypdfium2.version as version

        ocr_service, docling_service = OcrService(self.db), DoclingService(self.db)
        ocr = (
            ocr_service.require()
            if use_ocr or (auto_enhance and ocr_service.status()["configured"])
            else None
        )
        docling = (
            docling_service.require()
            if use_docling or (auto_enhance and docling_service.status()["configured"])
            else None
        )
        configuration = {
            **PARSER_CONFIG,
            "pypdfium": str(version.PYPDFIUM_INFO),
            "pdfium": str(version.PDFIUM_INFO),
            **({"ocr": ocr["fingerprint"]} if ocr else {}),
            **(
                {
                    "docling": docling["fingerprint"],
                    "pipeline": "quality-route-candidate-v1"
                    if auto_enhance
                    else docling["fingerprint"]["pipeline"],
                }
                if docling
                else {}
            ),
            "base_revision": expected,
            "page_numbers": selection,
            **({"routing": ROUTE_POLICY} if auto_enhance else {}),
        }
        fingerprint = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
        payload = {
            "doc_version_id": doc_version_id,
            "fingerprint": fingerprint,
            "base_revision": expected,
            **{
                name: value
                for name, value in options.items()
                if value is not False and value is not None
            },
        }
        if existing and old_payload.get("fingerprint") != fingerprint:
            raise EngineError("PARSER_FINGERPRINT_CHANGED")
        job = existing or self.jobs.enqueue(
            "parse_page",
            key,
            payload,
        )
        if queue_only:
            return job
        if job["status"] == "completed":
            return self.jobs.get(job["id"])
        claimed = self.jobs.claim(job["id"], lease_seconds=360)
        if claimed is None:
            return self.jobs.get(job["id"])
        token, run_id = claimed["lease_token"], str(uuid4())
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO parse_runs(id,doc_version_id,fingerprint,status,created_at) VALUES(?,?,?,'running',?)",
                (run_id, doc_version_id, fingerprint, utc_now()),
            )
        try:
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job["id"], token)
                self.jobs.event(
                    conn,
                    job["id"],
                    "parser_fingerprint",
                    {
                        "parse_run_id": run_id,
                        "configuration": configuration,
                    },
                )

            heartbeat = time.monotonic()
            started = time.monotonic()

            def check():
                nonlocal heartbeat
                if parent_check:
                    parent_check()
                with self.db.connection() as conn:
                    self.jobs.require_lease(conn, job["id"], token)
                if time.monotonic() - started > 700:
                    raise EngineError("PDF_WORKER_TIMEOUT")
                if time.monotonic() - heartbeat > 20:
                    self.jobs.heartbeat(job["id"], token, seconds=360)
                    heartbeat = time.monotonic()

            request = {"pdf_path": str(path), **({"page_numbers": selection} if selection else {})}
            if auto_enhance:
                content = self._automatic(run_id, job, token, request, ocr, docling, check)
            else:
                content = self._attempt(
                    run_id,
                    job,
                    token,
                    "docling" if docling else "ocr" if ocr else "native_text",
                    {
                        **request,
                        **(
                            {
                                "docling_directory": docling["directory"],
                                "docling_fingerprint": docling["fingerprint"],
                            }
                            if docling
                            else {}
                        ),
                        **(
                            {
                                "ocr_directory": ocr["directory"],
                                "ocr_fingerprint": ocr["fingerprint"],
                            }
                            if ocr
                            else {}
                        ),
                    },
                    check=check,
                )
            pages = content["pages"]
            total_pages = content.get("document_page_count", len(pages))
            expected_pages = selection or list(range(1, total_pages + 1))
            if (
                type(total_pages) is not int
                or not 0 < total_pages <= 500
                or not 0 < len(pages) <= 500
                or sorted(p["page_number"] for p in pages) != expected_pages
            ):
                raise EngineError("PAGE_LIMIT")
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job["id"], token)
                if parent_check:
                    parent_check(conn)
                if (
                    conn.execute(
                        "SELECT 1 FROM document_versions WHERE id=? AND visibility='visible'",
                        (doc_version_id,),
                    ).fetchone()
                    is None
                ):
                    raise EngineError("SCOPE_NOT_AVAILABLE", status=409)
                begin_publish(conn, doc_version_id, expected, selection, total_pages)
                elements = {}
                for page in pages:
                    element_id = str(uuid4())
                    elements[page["page_number"]] = element_id
                    quality = (
                        "docling_partial_unreviewed"
                        if page["error_code"] and page.get("method") == "docling"
                        else "failed"
                        if page["error_code"]
                        else "needs_ocr_or_review"
                        if not page["text"].strip()
                        else "ocr_low_confidence_unreviewed"
                        if page.get("method") == "ocr"
                        and (page.get("mean_confidence") or 0) < POLICY["min_mean_confidence"]
                        else "ocr_extracted_unreviewed"
                        if page.get("method") == "ocr"
                        else "docling_extracted_unreviewed"
                        if page.get("method") == "docling"
                        else "text_extracted_unreviewed"
                    )
                    conn.execute(
                        "INSERT INTO elements VALUES(?,?,?,?,?,?,?)",
                        (
                            element_id,
                            run_id,
                            page["page_number"],
                            page["text"],
                            quality,
                            page["error_code"],
                            page["rotation"],
                        ),
                    )
                    conn.execute(
                        "INSERT INTO published_pages VALUES(?,?,?)",
                        (doc_version_id, page["page_number"], element_id),
                    )
                    if "blocks" in page:
                        conn.execute(
                            "INSERT INTO parse_page_structure VALUES(?,?)",
                            (element_id, json.dumps(page["blocks"], ensure_ascii=False)),
                        )
                    for chunk in chunk_page(page["text"]):
                        chunk_id = str(uuid4())
                        conn.execute(
                            "INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?,1)",
                            (
                                chunk_id,
                                doc_version_id,
                                run_id,
                                element_id,
                                chunk["content_sha256"],
                                chunk["text"],
                                chunk["start"],
                                chunk["end"],
                                page["page_number"],
                            ),
                        )
                        conn.execute(
                            "INSERT INTO chunks_fts VALUES(?,?)", (chunk_id, chunk["text"])
                        )
                        index_terms(conn, chunk_id, chunk["text"])
                persist_tables(conn, run_id, doc_version_id, elements, content.get("tables", []))
                conn.execute(
                    "INSERT INTO published_tables SELECT id,doc_version_id FROM parse_tables WHERE parse_run_id=?",
                    (run_id,),
                )
                # The structure budget applies to the published document, even
                # when it contains pages from several selective ParseRuns.
                if (
                    conn.execute(
                        "SELECT COUNT(*) FROM published_tables WHERE doc_version_id=?",
                        (doc_version_id,),
                    ).fetchone()[0]
                    > DOCLING_POLICY["max_tables"]
                    or conn.execute(
                        "SELECT COUNT(*) FROM table_cells c JOIN published_tables p ON p.table_id=c.table_id WHERE p.doc_version_id=?",
                        (doc_version_id,),
                    ).fetchone()[0]
                    > DOCLING_POLICY["max_cells"]
                ):
                    raise EngineError("DOCLING_STRUCTURE_LIMIT")
                status = finish_publish(
                    conn,
                    doc_version_id,
                    run_id,
                    expected,
                    total_pages,
                    content.get("unresolved_items", 0),
                    len(content.get("unlocated_items", [])),
                    selection,
                )
                conn.execute(
                    "UPDATE parse_runs SET status=?,page_count=?,finished_at=? WHERE id=?",
                    (status, len(pages), utc_now(), run_id),
                )
                conn.execute(
                    "UPDATE document_versions SET parse_status=? WHERE id=?",
                    (status, doc_version_id),
                )
                self.jobs.event(
                    conn,
                    job["id"],
                    "parser_result",
                    {
                        "parse_run_id": run_id,
                        "tables": len(content.get("tables", [])),
                        "unresolved_items": content.get("unresolved_items", 0),
                        "routing": content.get("routing", []),
                        "publication_revision": expected + 1,
                        "unlocated_items": revision(conn, doc_version_id)["unlocated_items"],
                        "pages": [
                            {
                                "page_number": page["page_number"],
                                "method": page.get("method", "native_text"),
                                "mean_confidence": page.get("mean_confidence"),
                            }
                            for page in pages
                        ],
                    },
                )
                self.jobs.complete(job["id"], token, "parse_run:" + run_id, connection=conn)
            return self.jobs.get(job["id"])
        except Exception as exc:
            code = exc.code if isinstance(exc, EngineError) else "PDF_EXTRACTION_FAILED"
            self.jobs.fail(job["id"], token, code)
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE parse_runs SET status='failed',error_code=?,finished_at=? WHERE id=?",
                    (code, utc_now(), run_id),
                )
            if isinstance(exc, EngineError):
                raise
            raise EngineError(code) from exc

    def _attempt(self, run_id, job, token, method, request, *, check):
        attempt_id = str(uuid4())
        with self.db.transaction() as conn:
            self.jobs.require_lease(conn, job["id"], token)
            conn.execute(
                "INSERT INTO parse_attempts VALUES(?,?,?,'running',?,NULL,NULL,?,NULL)",
                (attempt_id, run_id, method, json.dumps(request.get("page_numbers")), utc_now()),
            )
        try:
            result = run_worker(
                request,
                timeout=40 if method == "native_text" else 300,
                check=check,
                log_directory=self.db.path.parent / "parse-worker-logs",
            )
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job["id"], token)
                conn.execute(
                    "UPDATE parse_attempts SET status='completed',result_json=?,finished_at=? WHERE id=?",
                    (json.dumps(result, ensure_ascii=False), utc_now(), attempt_id),
                )
            return result
        except Exception as exc:
            code = exc.code if isinstance(exc, EngineError) else "PDF_EXTRACTION_FAILED"
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE parse_attempts SET status='failed',error_code=?,finished_at=? WHERE id=?",
                    (code, utc_now(), attempt_id),
                )
            raise

    def _automatic(self, run_id, job, token, request, ocr, docling, check):
        native = self._attempt(
            run_id, job, token, "native_text", {**request, "quality_probe": True}, check=check
        )
        decisions = choose(
            native["pages"], ocr_available=ocr is not None, docling_available=docling is not None
        )
        result = {
            **native,
            "pages": [dict(p) for p in native["pages"]],
            "tables": [],
            "routing": decisions,
            "unresolved_items": 0,
            "unlocated_items": [],
        }
        mapping = {p["page_number"]: p for p in result["pages"]}
        for d in decisions:
            if d["desired_method"] != "native_text" and d["method"] == "native_text":
                mapping[d["page_number"]]["error_code"] = "AUTO_ENHANCEMENT_UNAVAILABLE"
        for method, resource in (("ocr", ocr), ("docling", docling)):
            selected = [d["page_number"] for d in decisions if d["method"] == method]
            if not selected:
                continue
            try:
                enhanced = self._attempt(
                    run_id,
                    job,
                    token,
                    method,
                    {
                        **request,
                        "page_numbers": selected,
                        method + "_directory": resource["directory"],
                        method + "_fingerprint": resource["fingerprint"],
                        **({"force_ocr_pages": selected} if method == "ocr" else {}),
                    },
                    check=check,
                )
                by_page = {p["page_number"]: p for p in enhanced["pages"]}
                if set(by_page) != set(selected):
                    raise EngineError("DOCLING_STRUCTURE_INVALID")
            except EngineError as exc:
                if exc.code in {"LEASE_LOST", "JOB_CANCELLED", "PARSE_PUBLICATION_CHANGED"}:
                    raise
                # Explicit audit/diagnostic, never silently convert a lost lease
                # or arbitrary implementation exception into a successful parse.
                check()
                for d in decisions:
                    if d["method"] == method:
                        d.update(accepted=False, enhancement_error=exc.code)
                        mapping[d["page_number"]]["error_code"] = "AUTO_ENHANCEMENT_FAILED"
                continue
            accepted = set()
            for d in decisions:
                if d["method"] != method:
                    continue
                number = d["page_number"]
                ok, reason = accept(mapping[number], by_page[number])
                d.update(accepted=ok, acceptance_reason=reason)
                if ok:
                    mapping[number].clear()
                    mapping[number].update(by_page[number])
                    accepted.add(number)
                else:
                    mapping[number]["error_code"] = "AUTO_ENHANCEMENT_REJECTED"
            result["tables"].extend(
                t for t in enhanced.get("tables", []) if t["page_number"] in accepted
            )
            result["unresolved_items"] += len(enhanced.get("unlocated_items", []))
            result["unlocated_items"].extend(enhanced.get("unlocated_items", []))
        return result
