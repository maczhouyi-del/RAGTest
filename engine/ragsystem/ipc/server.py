import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path
from threading import BoundedSemaphore

from fastapi import BackgroundTasks, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ragsystem import __version__
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.ipc.grants import Grants
from ragsystem.jobs.repository import Jobs
from ragsystem.library.annotations import Annotations
from ragsystem.library.identity import Identity
from ragsystem.library.lifecycle import Lifecycle
from ragsystem.library.repository import Library, MetadataUpdate
from ragsystem.parsing.docling import DoclingService
from ragsystem.parsing.ocr import OcrService
from ragsystem.parsing.pipeline import Parser
from ragsystem.parsing.tables import Tables
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.backup_service import BackupService
from ragsystem.storage.database import Database
from ragsystem.workflows.history import History
from ragsystem.workflows.workbench import Workbench

MAX_REQUEST_BYTES = 16 * 1024
MAX_SCOPE_REQUEST_BYTES = 128 * 1024
SCOPE_ENDPOINTS = {
    "/v0/search",
    "/v0/answers",
    "/v0/research",
    "/v0/document-merges",
    "/v0/mvp/prepare",
}


class LocalBoundary:
    """Authenticate before routing/body parsing; no CORS or browser access."""

    def __init__(self, app, token):
        self.app, self.token = app, token.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope.get("headers", [])

        async def reject(status, code):
            response = JSONResponse(
                {"code": code, "message": code, "retriable": False}, status_code=status
            )
            await response(scope, receive, send)

        tokens = [v for k, v in headers if k.lower() == b"x-rag-session"]
        if len(tokens) != 1 or not hmac.compare_digest(tokens[0], self.token):
            return await reject(401, "SESSION_INVALID")
        host = next((v for k, v in headers if k.lower() == b"host"), b"")
        if host.split(b":", 1)[0] != b"127.0.0.1" or any(
            k.lower() == b"origin" for k, _ in headers
        ):
            return await reject(403, "BROWSER_REQUEST_FORBIDDEN")
        if scope["method"] not in {"GET", "POST"}:
            return await reject(405, "METHOD_NOT_ALLOWED")
        request_limit = (
            MAX_SCOPE_REQUEST_BYTES if scope["path"] in SCOPE_ENDPOINTS else MAX_REQUEST_BYTES
        )
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > request_limit:
                return await reject(413, "REQUEST_TOO_LARGE")
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GrantRequest(StrictModel):
    path: str = Field(min_length=1, max_length=4096)


class ImportRequest(StrictModel):
    file_grant_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=200)
    project_id: str | None = Field(default=None, min_length=1, max_length=100)


class TableReviewRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    status: str = Field(pattern="^(unreviewed|confirmed|rejected|uncertain)$")
    note: str = Field(min_length=1, max_length=4000)


class ParseRequest(StrictModel):
    use_ocr: bool = False
    use_docling: bool = False
    auto_enhance: bool = False
    page_numbers: list[int] | None = Field(default=None, min_length=1, max_length=40)
    idempotency_key: str = Field(min_length=1, max_length=200)


class BatchImportRequest(StrictModel):
    file_grant_ids: list[str] = Field(min_length=1, max_length=32)
    idempotency_key: str = Field(min_length=1, max_length=150)
    project_id: str | None = Field(default=None, min_length=1, max_length=100)


class MetadataFilter(StrictModel):
    tag: str | None = Field(default=None, min_length=1, max_length=100)
    year_from: int | None = Field(default=None, ge=1500, le=2200)
    year_to: int | None = Field(default=None, ge=1500, le=2200)


class SearchRequest(StrictModel):
    filters: MetadataFilter | None = None
    query: str = Field(min_length=1, max_length=20000)
    strategy: str = Field(pattern="^(fts_only|keyword|vector_exact|hybrid)$")
    authorized_doc_version_ids: list[str] = Field(min_length=1, max_length=1000)
    k: int = Field(ge=1, le=100)
    project_id: str | None = Field(default=None, min_length=1, max_length=100)


class ProjectRequest(StrictModel):
    name: str = Field(min_length=1, max_length=100)


class LifecycleRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    state: str = Field(pattern="^(active|archived|retracted)$")
    note: str = Field(min_length=1, max_length=4000)


class MembershipRequest(StrictModel):
    linked: bool


class DirectoryRequest(StrictModel):
    path: str = Field(min_length=1, max_length=4096)
    purpose: str = Field(
        pattern="^(backup_parent|snapshot|restore_parent|embedding|generator|ocr|docling)$"
    )


class BackupRequest(StrictModel):
    parent_grant_id: str = Field(min_length=1, max_length=100)
    source_grant_id: str | None = Field(default=None, min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=200)


class IndexRequest(StrictModel):
    model_grant_id: str = Field(min_length=1, max_length=100)
    backend: str = Field(pattern="^(sqlite-vec|lancedb)$")
    idempotency_key: str = Field(min_length=1, max_length=200)


class MergeRequest(StrictModel):
    source_id: str = Field(min_length=1, max_length=100)
    target_id: str = Field(min_length=1, max_length=100)
    expected_version_ids: list[str] = Field(min_length=2, max_length=1000)


class AnnotationRequest(StrictModel):
    annotation_id: str | None = Field(default=None, min_length=1, max_length=100)
    source_anchor_id: str | None = Field(default=None, min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)
    page_number: int = Field(ge=1, le=500)
    note: str = Field(min_length=1, max_length=4000)


class GeneratorRequest(StrictModel):
    model_grant_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=200)


class AnswerRequest(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    version_ids: list[str] = Field(min_length=1, max_length=1000)
    project_id: str | None = Field(default=None, min_length=1, max_length=100)
    mode: str = Field(pattern="^(extractive|generative)$")
    strategy: str = Field(
        default="keyword",
        pattern="^(fts_only|keyword|vector_exact|hybrid|keyword_review|hybrid_review)$",
    )
    conversation_id: str | None = Field(default=None, min_length=1, max_length=100)
    provider_id: str | None = Field(default=None, min_length=1, max_length=100)
    allow_external: bool = False
    provider_revision: int | None = Field(default=None, ge=1)
    per_paper_limit: int = Field(default=3, ge=1, le=8)


class ResearchRequest(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    fields: list[str] = Field(min_length=1, max_length=20)
    version_ids: list[str] = Field(min_length=1, max_length=1000)
    project_id: str | None = Field(default=None, min_length=1, max_length=100)
    mode: str = Field(pattern="^(extractive|generative)$")


class ReviewRequest(StrictModel):
    status: str = Field(pattern="^(unreviewed|confirmed|rejected)$")
    note: str = Field(default="", max_length=4000)


class ObservationRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    value: str = Field(min_length=1, max_length=2000)
    unit: str = Field(default="", max_length=100)
    experiment_id: str = Field(min_length=1, max_length=200)
    meaning_status: str = Field(pattern="^(reported|explicit_not_reported|evidence_insufficient)$")
    conditions_status: str = Field(pattern="^(not_assessed|comparable|not_comparable|unknown)$")
    conditions: dict[str, str] = Field(default_factory=dict, max_length=10)


def public_job(row):
    return {
        "job_id": row["id"],
        "label": json.loads(row["payload_json"]).get("display_name", row["type"]),
        **{
            key: row[key]
            for key in (
                "type",
                "status",
                "attempt_count",
                "max_attempts",
                "error_code",
                "result_ref",
                "updated_at",
            )
        },
    }


def create_app(token: str, data_root: Path):
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise EngineError("INVALID_STARTUP_TOKEN")
    data_root = Path(data_root)
    db = Database(data_root / "data" / "research.db")
    jobs, grants = Jobs(db), Grants()
    importer = PdfImporter(db, data_root)
    parser, sources = Parser(db, data_root), Sources(db, data_root)
    library = Library(db)
    directories, backups = Directories(), BackupService(db, data_root)
    hybrid = HybridSearch(db, data_root)
    workbench = Workbench(db, data_root, hybrid)
    slot = BoundedSemaphore(1)

    @asynccontextmanager
    async def lifespan(app):
        # Published immutable objects may safely finish expired import intents.
        importer.recover_published_imports()
        yield
        grants.close()
        generator = workbench.generation.generator
        if generator is not None and hasattr(generator, "close"):
            generator.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(LocalBoundary, token=token)
    app.state.workbench = workbench

    @app.exception_handler(EngineError)
    async def domain_error(request, exc):
        return JSONResponse(
            {"code": exc.code, "message": exc.code, "retriable": exc.retriable},
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Pydantic error inputs could contain broker paths or private source text.
        return JSONResponse(
            {"code": "INVALID_REQUEST", "message": "INVALID_REQUEST", "retriable": False},
            status_code=400,
        )

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse(
            {"code": "INTERNAL_ERROR", "message": "INTERNAL_ERROR", "retriable": False},
            status_code=500,
        )

    @app.get("/v0/health")
    def health():
        return {
            "status": "ready",
            "sidecar_version": __version__,
            "api_revision": "0.2-local",
            "schema_version": "0.1-draft",
            "capabilities": [
                "pdf_storage",
                "durable_jobs",
                "page_text",
                "fts_sources",
                "projects",
                "manual_metadata",
                "pdf_reader",
                "batch_import",
                "immutable_backup_restore",
                "keyword_search",
                "candidate_vectors",
                "evidence_drafts",
                "per_paper_research",
                "human_reviews",
                "report_revisions",
                "reading_notes",
                "document_versions",
            ],
            "disabled_reasons": ["OCR_NOT_CONFIGURED", "WINDOWS_NOT_VERIFIED"]
            + ([] if hybrid.status()["ready"] else ["EMBEDDING_NOT_CONFIGURED"])
            + ([] if workbench.generation.status()["configured"] else ["GENERATOR_NOT_CONFIGURED"]),
        }

    @app.post("/v0/internal/file-grants")
    def issue_grant(body: GrantRequest):
        grant = grants.issue(Path(body.path))
        return {"file_grant_id": grant.id, "sha256": grant.sha256, "size_bytes": grant.size}

    def run_import(job, grant):
        try:
            importer.run(job, grant)
        except EngineError:
            pass  # importer persisted an explicit failed/cancelled status.
        except Exception:
            jobs.fail(job["id"], job["lease_token"], "IMPORT_INTERNAL_ERROR")
        finally:
            slot.release()

    @app.post("/v0/imports", status_code=202)
    def queue_import(body: ImportRequest, background: BackgroundTasks):
        existing = jobs.find_key("import", body.idempotency_key)
        if existing:
            payload = json.loads(existing["payload_json"])
            if (
                payload.get("grant_id") != body.file_grant_id
                or payload.get("project_id") != body.project_id
            ):
                raise EngineError("IDEMPOTENCY_CONFLICT", status=409)
            return {"job_id": existing["id"], "status": existing["status"]}
        if body.project_id is not None:
            with db.connection() as conn:
                library.require_project(conn, body.project_id)
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429, retriable=True)
        grant = None
        try:
            grant = grants.take(body.file_grant_id)
            row = jobs.enqueue(
                "import",
                body.idempotency_key,
                {
                    "grant_id": grant.id,
                    "sha256": grant.sha256,
                    "display_name": grant.display_name,
                    "project_id": body.project_id,
                },
            )
            claimed = jobs.claim(row["id"])
            if claimed is None:
                raise EngineError("JOB_NOT_RUNNABLE", status=409)
            background.add_task(run_import, claimed, grant)
            return {"job_id": row["id"], "status": "running"}
        except BaseException:
            slot.release()
            if grant:
                grant.source.close()
            raise

    @app.get("/v0/jobs")
    def list_jobs():
        return {"jobs": [public_job(row) for row in jobs.list()]}

    def run_batch(items):
        try:
            for row, grant in items:
                claimed = jobs.claim(row["id"])
                if not claimed:
                    grant.source.close()
                    continue
                try:
                    importer.run(claimed, grant)
                except Exception as exc:
                    jobs.fail(
                        row["id"],
                        claimed["lease_token"],
                        exc.code if isinstance(exc, EngineError) else "IMPORT_INTERNAL_ERROR",
                    )
        finally:
            for _, grant in items:
                if not grant.source.closed:
                    grant.source.close()
            slot.release()

    @app.post("/v0/import-batches", status_code=202)
    def import_batch(body: BatchImportRequest, background: BackgroundTasks):
        if len(set(body.file_grant_ids)) != len(body.file_grant_ids):
            raise EngineError("INVALID_REQUEST")
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        items, output = [], []
        try:
            if body.project_id is not None:
                with db.connection() as conn:
                    library.require_project(conn, body.project_id)
            for index, identifier in enumerate(body.file_grant_ids):
                key = body.idempotency_key + ":" + str(index)
                existing = jobs.find_key("import", key)
                if existing:
                    payload = json.loads(existing["payload_json"])
                    if (
                        payload.get("grant_id") != identifier
                        or payload.get("project_id") != body.project_id
                    ):
                        raise EngineError("IDEMPOTENCY_CONFLICT", status=409)
                    output.append(public_job(existing))
                    continue
                grant = grants.take(identifier)
                row = jobs.enqueue(
                    "import",
                    key,
                    {
                        "grant_id": identifier,
                        "sha256": grant.sha256,
                        "display_name": grant.display_name,
                        "project_id": body.project_id,
                    },
                )
                items.append((row, grant))
                output.append(public_job(row))
            background.add_task(run_batch, items)
            return {"jobs": output}
        except BaseException:
            for row, grant in items:
                grant.source.close()
                jobs.cancel(row["id"])
            slot.release()
            raise

    @app.get("/v0/jobs/{job_id}")
    def get_job(job_id: str):
        return public_job(jobs.get(job_id))

    @app.post("/v0/jobs/{job_id}/cancel", status_code=202)
    def cancel(job_id: str):
        row = jobs.cancel(job_id)
        return {"job_id": row["id"], "status": row["status"]}

    @app.get("/v0/documents")
    def documents(project_id: str | None = None):
        return {"documents": library.list_documents(project_id)}

    @app.get("/v0/projects")
    def projects():
        return {"projects": library.list_projects()}

    @app.post("/v0/projects", status_code=201)
    def create_project(body: ProjectRequest):
        return library.create_project(body.name)

    @app.post("/v0/projects/{project_id}/documents/{document_id}")
    def membership(project_id: str, document_id: str, body: MembershipRequest):
        return library.set_membership(project_id, document_id, body.linked)

    @app.post("/v0/documents/{document_id}/metadata")
    def edit_metadata(document_id: str, body: MetadataUpdate):
        return library.update_metadata(document_id, body)

    @app.get("/v0/lifecycle")
    def lifecycle_records():
        return {"records": Lifecycle(db).records()}

    @app.post("/v0/documents/{document_id}/lifecycle")
    def update_lifecycle(document_id: str, body: LifecycleRequest):
        return Lifecycle(db).update(document_id, body.expected_revision, body.state, body.note)

    @app.get("/v0/documents/{version_id}/parse-diagnostics")
    def parse_diagnostics(version_id: str):
        return library.parse_diagnostics(version_id)

    @app.get("/v0/documents/{version_id}/tables")
    def table_list(version_id: str, offset: int = 0):
        if not 0 <= offset <= 200:
            raise EngineError("INVALID_PAGE")
        return Tables(db).list(version_id, offset)

    @app.get("/v0/tables/{table_id}")
    def table_content(table_id: str, row_offset: int = 0):
        if not 0 <= row_offset <= 1000:
            raise EngineError("INVALID_PAGE")
        return Tables(db).get(table_id, row_offset)

    @app.post("/v0/tables/{table_id}/review")
    def table_review(table_id: str, body: TableReviewRequest):
        return Tables(db).review(table_id, body)

    @app.get("/v0/documents/{version_id}/file")
    def document_file(version_id: str):
        return library.file_record(version_id, data_root)

    def run_parse(
        version_id, key, use_ocr=False, use_docling=False, auto_enhance=False, page_numbers=None
    ):
        try:
            parser.parse(
                version_id,
                key,
                use_ocr=use_ocr,
                use_docling=use_docling,
                auto_enhance=auto_enhance,
                page_numbers=page_numbers,
            )
        except Exception as exc:
            # A source could change after queueing but before claiming. Persist
            # that pre-claim failure too, rather than leaving a queued ghost.
            job = jobs.find_key("parse_page", key)
            if job and job["status"] in {"queued", "retry_wait"}:
                claimed = jobs.claim(job["id"])
                if claimed:
                    jobs.fail(
                        job["id"],
                        claimed["lease_token"],
                        exc.code if isinstance(exc, EngineError) else "PARSE_INTERNAL_ERROR",
                    )
        finally:
            slot.release()

    @app.post("/v0/documents/{version_id}/parse", status_code=202)
    def parse_document(version_id: str, body: ParseRequest, background: BackgroundTasks):
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429, retriable=True)
        try:
            job = parser.parse(
                version_id,
                body.idempotency_key,
                queue_only=True,
                use_ocr=body.use_ocr,
                use_docling=body.use_docling,
                auto_enhance=body.auto_enhance,
                page_numbers=body.page_numbers,
            )
            background.add_task(
                run_parse,
                version_id,
                body.idempotency_key,
                body.use_ocr,
                body.use_docling,
                body.auto_enhance,
                body.page_numbers,
            )
            return {"job_id": job["id"], "status": job["status"]}
        except BaseException:
            slot.release()
            raise

    @app.post("/v0/search")
    def source_search(body: SearchRequest):
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            return hybrid.search(
                body.query,
                body.authorized_doc_version_ids,
                body.k,
                body.project_id,
                body.strategy,
                filters=body.filters.model_dump() if body.filters else None,
            )
        finally:
            slot.release()

    @app.get("/v0/index")
    def index_status():
        return hybrid.status()

    def run_index(job_id, model, backend):
        try:
            hybrid.build(job_id, model, backend)
        finally:
            slot.release()

    @app.post("/v0/index", status_code=202)
    def build_index(body: IndexRequest, background: BackgroundTasks):
        existing = jobs.find_key("embed_batch", body.idempotency_key)
        payload = {"backend": body.backend, "model_grant_id": body.model_grant_id}
        if existing:
            row = jobs.enqueue("embed_batch", body.idempotency_key, payload)
            return {"job_id": row["id"], "status": row["status"]}
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            model = directories.take(body.model_grant_id, "embedding")
            row = jobs.enqueue(
                "embed_batch",
                body.idempotency_key,
                {"backend": body.backend, "model_grant_id": body.model_grant_id},
            )
            background.add_task(run_index, row["id"], model, body.backend)
            return {"job_id": row["id"], "status": row["status"]}
        except BaseException:
            slot.release()
            raise

    @app.get("/v0/source-anchors/{anchor_id}")
    def source_anchor(anchor_id: str):
        return sources.anchor(anchor_id)

    @app.post("/v0/internal/directory-grants")
    def directory_grant(body: DirectoryRequest):
        grant = directories.issue(Path(body.path), body.purpose)
        return {"directory_grant_id": grant.id, "label": grant.path.name}

    @app.get("/v0/backups")
    def backup_records():
        return {"records": backups.records()}

    def run_backup(job_id, parent, source):
        try:
            backups.run(job_id, parent, source)
        finally:
            slot.release()

    @app.post("/v0/backups", status_code=202)
    def queue_backup(body: BackupRequest, background: BackgroundTasks):
        payload = body.model_dump(exclude={"idempotency_key"})
        existing = jobs.find_key("backup", body.idempotency_key)
        if existing:
            row = jobs.enqueue("backup", body.idempotency_key, payload)
            return {"job_id": row["id"], "status": row["status"]}
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            source = (
                directories.take(body.source_grant_id, "snapshot") if body.source_grant_id else None
            )
            parent = directories.take(
                body.parent_grant_id, "restore_parent" if source else "backup_parent"
            )
            row = jobs.enqueue("backup", body.idempotency_key, payload)
            background.add_task(run_backup, row["id"], parent, source)
            return {"job_id": row["id"], "status": row["status"]}
        except BaseException:
            slot.release()
            raise

    @app.get("/v0/internal/restored-workspaces/{identifier}")
    def restored_workspace(identifier: str):
        return {"data_root": str(backups.restored_path(identifier))}

    def run_retry(row):
        try:
            if row["type"] == "import":
                importer.resume(row["id"])
            else:
                payload = json.loads(row["payload_json"])
                parser.parse(
                    payload["doc_version_id"],
                    row["idempotency_key"],
                    use_ocr=payload.get("use_ocr", False),
                    use_docling=payload.get("use_docling", False),
                    auto_enhance=payload.get("auto_enhance", False),
                    page_numbers=payload.get("page_numbers"),
                )
        except Exception as exc:
            current = jobs.get(row["id"])
            if current["status"] == "queued":
                current = jobs.claim(row["id"])
            if current:
                jobs.fail(
                    row["id"],
                    current["lease_token"],
                    exc.code if isinstance(exc, EngineError) else "RETRY_FAILED",
                )
        finally:
            slot.release()

    @app.post("/v0/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str, background: BackgroundTasks):
        jobs.recover_expired()
        row = jobs.get(job_id)
        payload = json.loads(row["payload_json"])
        if row["type"] == "import":
            digest = payload.get("sha256", "")
            if (
                len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
                or not (data_root / "papers" / (digest + ".pdf")).is_file()
            ):
                raise EngineError("RESELECT_FILE_REQUIRED", status=409)
        elif row["type"] == "parse_page":
            parser.parse(
                payload["doc_version_id"],
                row["idempotency_key"],
                queue_only=True,
                use_ocr=payload.get("use_ocr", False),
                use_docling=payload.get("use_docling", False),
                auto_enhance=payload.get("auto_enhance", False),
                page_numbers=payload.get("page_numbers"),
            )
        else:
            raise EngineError("REAUTHORIZE_REQUIRED", status=409)
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            row = jobs.retry(job_id)
            background.add_task(run_retry, row)
            return {"job_id": row["id"], "status": row["status"]}
        except BaseException:
            slot.release()
            raise

    @app.get("/v0/document-merges")
    def merge_records():
        return {"records": Identity(db).records()}

    @app.post("/v0/document-merges", status_code=201)
    def merge_documents(body: MergeRequest):
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            return Identity(db).merge(body.source_id, body.target_id, body.expected_version_ids)
        finally:
            slot.release()

    @app.post("/v0/document-merges/{merge_id}/undo")
    def undo_merge(merge_id: str):
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            return Identity(db).undo(merge_id)
        finally:
            slot.release()

    @app.get("/v0/documents/{version_id}/annotations")
    def annotations(version_id: str):
        return {"annotations": Annotations(db, data_root).list(version_id)}

    @app.post("/v0/documents/{version_id}/annotations")
    def save_annotation(version_id: str, body: AnnotationRequest):
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            return Annotations(db, data_root).save(version_id, body)
        finally:
            slot.release()

    @app.get("/v0/docling")
    def docling_status():
        return DoclingService(db).status()

    def run_docling_configuration(job_id, grant):
        job = jobs.claim(job_id, lease_seconds=180)
        try:
            if job:
                DoclingService(db).configure(grant, job)
        except Exception as exc:
            if job:
                jobs.fail(
                    job_id,
                    job["lease_token"],
                    exc.code if isinstance(exc, EngineError) else "DOCLING_LOAD_FAILED",
                )
        finally:
            slot.release()

    @app.post("/v0/docling", status_code=202)
    def configure_docling(body: GeneratorRequest, background: BackgroundTasks):
        payload = {"model_grant_id": body.model_grant_id, "action": "configure_docling"}
        if jobs.find_key("verify", body.idempotency_key):
            return public_job(jobs.enqueue("verify", body.idempotency_key, payload))
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            grant = directories.take(body.model_grant_id, "docling")
            row = jobs.enqueue("verify", body.idempotency_key, payload)
            background.add_task(run_docling_configuration, row["id"], grant)
            return public_job(row)
        except BaseException:
            slot.release()
            raise

    @app.get("/v0/ocr")
    def ocr_status():
        return OcrService(db).status()

    def run_ocr_configuration(job_id, grant):
        job = jobs.claim(job_id, lease_seconds=180)
        try:
            if job:
                OcrService(db).configure(grant, job)
        except Exception as exc:
            if job:
                jobs.fail(
                    job_id,
                    job["lease_token"],
                    exc.code if isinstance(exc, EngineError) else "OCR_LOAD_FAILED",
                )
        finally:
            slot.release()

    @app.post("/v0/ocr", status_code=202)
    def configure_ocr(body: GeneratorRequest, background: BackgroundTasks):
        payload = {"model_grant_id": body.model_grant_id, "action": "configure_ocr"}
        if jobs.find_key("verify", body.idempotency_key):
            return public_job(jobs.enqueue("verify", body.idempotency_key, payload))
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            grant = directories.take(body.model_grant_id, "ocr")
            row = jobs.enqueue("verify", body.idempotency_key, payload)
            background.add_task(run_ocr_configuration, row["id"], grant)
            return public_job(row)
        except BaseException:
            slot.release()
            raise

    @app.get("/v0/generator")
    def generator_status():
        return workbench.generation.status()

    def run_generator(job_id, grant):
        job = jobs.claim(job_id, lease_seconds=1800)
        try:
            if job:
                workbench.generation.configure(grant, job)
        except Exception as exc:
            if job:
                jobs.fail(
                    job_id,
                    job["lease_token"],
                    exc.code if isinstance(exc, EngineError) else "MODEL_LOAD_FAILED",
                )
        finally:
            slot.release()

    @app.post("/v0/generator", status_code=202)
    def configure_generator(body: GeneratorRequest, background: BackgroundTasks):
        payload = {"model_grant_id": body.model_grant_id, "action": "load_generator"}
        if jobs.find_key("verify", body.idempotency_key):
            return public_job(jobs.enqueue("verify", body.idempotency_key, payload))
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            grant = directories.take(body.model_grant_id, "generator")
            row = jobs.enqueue("verify", body.idempotency_key, payload)
            background.add_task(run_generator, row["id"], grant)
            return public_job(row)
        except BaseException:
            slot.release()
            raise

    @app.get("/v0/history/{kind}")
    def history_index(
        kind: str, project_id: str | None = None, cursor: str | None = None, limit: int = 30
    ):
        return History(workbench).index(kind, project_id, cursor, limit)

    @app.get("/v0/answers/{run_id}")
    def answer_detail(run_id: str, project_id: str | None = None):
        return History(workbench).answer(run_id, project_id)

    @app.get("/v0/research/{plan_id}")
    def research_detail(
        plan_id: str,
        project_id: str | None = None,
        paper_offset: int = 0,
        observation_offset: int = 0,
    ):
        return History(workbench).research(plan_id, project_id, paper_offset, observation_offset)

    @app.get("/v0/answers")
    def answers(project_id: str | None = None):
        return {"answers": workbench.answers(project_id)}

    def run_workflow(kind, identifier, job_id=None):
        try:
            if kind == "answer":
                workbench.run_answer(identifier)
            else:
                workbench.execute_plan(identifier, job_id)
        finally:
            slot.release()

    @app.post("/v0/answers", status_code=202)
    def ask(body: AnswerRequest, background: BackgroundTasks):
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            row = workbench.create_answer(
                body.question,
                body.version_ids,
                body.project_id,
                body.mode,
                body.strategy,
                body.conversation_id,
                body.provider_id,
                body.allow_external,
                body.provider_revision,
                body.per_paper_limit,
            )
            background.add_task(run_workflow, "answer", row["id"])
            return row
        except BaseException:
            slot.release()
            raise

    @app.post("/v0/reviews/{target_id}")
    def review(target_id: str, body: ReviewRequest):
        return workbench.review(target_id, body.status, body.note)

    @app.get("/v0/research")
    def research(project_id: str | None = None):
        return {"plans": workbench.plans(project_id)}

    @app.post("/v0/research", status_code=201)
    def create_research(body: ResearchRequest):
        return workbench.create_plan(
            body.question, body.fields, body.version_ids, body.project_id, body.mode
        )

    @app.post("/v0/research/{plan_id}/run", status_code=202)
    def run_research(plan_id: str, background: BackgroundTasks):
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            with db.transaction() as conn:
                plan = conn.execute(
                    "SELECT * FROM research_plans WHERE id=?", (plan_id,)
                ).fetchone()
                if not plan:
                    raise EngineError("NOT_FOUND", status=404)
                if plan["status"] == "running":
                    raise EngineError("WORKER_BUSY", status=429)
                row = jobs.enqueue(
                    "research_extract",
                    str(__import__("uuid").uuid4()),
                    {"plan_id": plan_id},
                    connection=conn,
                )
            background.add_task(run_workflow, "research", plan_id, row["id"])
            return public_job(row)
        except BaseException:
            slot.release()
            raise

    @app.post("/v0/research/{plan_id}/observations/{evidence_id}")
    def edit_observation(plan_id: str, evidence_id: str, body: ObservationRequest):
        return workbench.edit_observation(plan_id, evidence_id, body.model_dump())

    @app.post("/v0/research/{plan_id}/reports", status_code=201)
    def create_report(plan_id: str):
        return workbench.report(plan_id)

    @app.get("/v0/reports/{report_id}")
    def report_content(report_id: str):
        return workbench.report_content(report_id)

    from ragsystem.ipc.mvp import register_mvp

    register_mvp(app, db, data_root, hybrid, workbench, jobs, slot)
    return app
