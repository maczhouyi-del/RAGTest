"""Real approved OCR resource integration; no assertion of scientific accuracy."""

import hashlib
import importlib.util
import json
import os
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.library.repository import Library
from ragsystem.parsing.ocr import OcrService, verify_directory
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.database import Database

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def ocr_directory():
    value = os.environ.get("RAGSYSTEM_OCR_MODEL_DIR")
    if not value or importlib.util.find_spec("tesserocr") is None:
        pytest.skip("explicit approved OCR resources/runtime required")
    return Path(value).resolve()


def scan_pdf(path):
    import pypdfium2 as pdfium

    with (
        pdfium.PdfDocument(ROOT / "tests/fixtures/public/N19-1423.pdf") as source,
        pdfium.PdfDocument.new() as output,
    ):
        page = source[0]
        bitmap = page.render(scale=200 / 72, grayscale=True)
        width, height = page.get_size()
        target = output.new_page(width, height)
        image = pdfium.PdfImage.new(output)
        image.set_bitmap(bitmap)
        image.set_matrix(pdfium.PdfMatrix(width, 0, 0, height, 0, 0))
        target.insert_obj(image)
        target.gen_content()
        output.save(path)
        target.close()
        bitmap.close()
        page.close()


def test_real_scan_ocr_scope_diagnostics_and_failed_replacement_preserves_text(
    tmp_path, ocr_directory
):
    root = tmp_path / "OCR 扫描 空格"
    root.mkdir()
    pdf = root / "scan.pdf"
    scan_pdf(pdf)
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(pdf, "scan")["doc_version_id"]
    parser = Parser(db, root)
    parser.parse(version, "native")
    assert Library(db).parse_diagnostics(version)["needs_ocr_pages"] == [1]
    grant = Directories().issue(ocr_directory, "ocr")
    jobs = Jobs(db)
    load = jobs.enqueue("verify", "ocr", {"action": "configure_ocr"})
    service = OcrService(db)
    service.configure(grant, jobs.claim(load["id"]))
    assert service.status()["configured"] and "directory" not in service.status()
    parser.parse(version, "ocr", use_ocr=True)
    diagnostics = Library(db).parse_diagnostics(version)
    assert diagnostics["pages"][0]["quality"] == "ocr_extracted_unreviewed"
    assert diagnostics["needs_ocr_pages"] == []
    assert diagnostics["runs"][0]["parser_configuration"]["ocr"] == service.status()["fingerprint"]
    sources = Sources(db, root)
    hits = sources.search("BERT", [version], 5)
    assert hits
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    anchor = sources.anchor(hits[0]["source_anchor_id"])
    assert (
        anchor["file_sha256"] == digest
        and anchor["location_level"] == "page_only"
        and anchor["bbox_norm"] is None
    )
    # A changed runtime fingerprint fails inside the real worker; old visible text survives.
    with db.transaction() as conn:
        config = json.loads(
            conn.execute("SELECT value_json FROM app_settings WHERE key='ocr'").fetchone()[0]
        )
        config["fingerprint"]["runtime_version"] = "wrong"
        conn.execute("UPDATE app_settings SET value_json=? WHERE key='ocr'", (json.dumps(config),))
    with pytest.raises(EngineError, match="OCR_FINGERPRINT_CHANGED"):
        parser.parse(version, "wrong-runtime", use_ocr=True)
    assert sources.anchor(hits[0]["source_anchor_id"]) == anchor
    assert hashlib.sha256((root / "papers" / (digest + ".pdf")).read_bytes()).hexdigest() == digest
    assert Library(db).parse_diagnostics(version)["runs"][0]["status"] == "failed"


def test_real_scan_auto_routes_to_approved_ocr_and_preserves_other_pages(tmp_path, ocr_directory):
    root = tmp_path / "automatic"
    root.mkdir()
    scan = root / "scan.pdf"
    scan_pdf(scan)
    mixed = root / "mixed.pdf"
    import pypdfium2 as pdfium

    with (
        pdfium.PdfDocument(ROOT / "tests/fixtures/public/N19-1423.pdf") as native,
        pdfium.PdfDocument(scan) as image,
        pdfium.PdfDocument.new() as pdf,
    ):
        pdf.import_pages(native, [0])
        pdf.import_pages(image, [0])
        pdf.save(mixed)
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(mixed, "mixed")["doc_version_id"]
    parser = Parser(db, root)
    parser.parse(version, "base")
    with db.connection() as conn:
        untouched = conn.execute(
            "SELECT element_id FROM published_pages WHERE page_number=1"
        ).fetchone()[0]
    jobs = Jobs(db)
    queued = jobs.enqueue("verify", "ocr", {})
    OcrService(db).configure(Directories().issue(ocr_directory, "ocr"), jobs.claim(queued["id"]))
    parser.parse(version, "automatic", auto_enhance=True, page_numbers=[2])
    diagnostics = Library(db).parse_diagnostics(version)
    decision = diagnostics["runs"][0]["routing"][0]
    assert decision["method"] == "ocr" and decision["accepted"]
    assert diagnostics["pages"][1]["quality"] == "ocr_extracted_unreviewed"
    assert len(diagnostics["runs"][0]["attempts"]) == 2
    with db.connection() as conn:
        assert (
            conn.execute("SELECT element_id FROM published_pages WHERE page_number=1").fetchone()[0]
            == untouched
        )


def test_ocr_resource_corruption_wrong_purpose_and_unconfigured_request(tmp_path):
    path = tmp_path / "resources"
    path.mkdir()
    (path / "eng.traineddata").write_bytes(b"unapproved")
    with pytest.raises(EngineError, match="OCR_MODEL_HASH_MISMATCH"):
        verify_directory(path)
    directories = Directories()
    grant = directories.issue(path, "embedding")
    with pytest.raises(EngineError, match="GRANT_INVALID"):
        directories.take(grant.id, "ocr")
    token = secrets.token_hex(32)
    root = tmp_path / "workspace"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "pdf"
    )["doc_version_id"]
    headers = {"X-RAG-Session": token}
    with TestClient(create_app(token, root), base_url="http://127.0.0.1") as client:
        assert client.get("/v0/ocr").status_code == 401
        assert client.get("/v0/ocr", headers=headers).json()["configured"] is False
        response = client.post(
            f"/v0/documents/{version}/parse",
            headers=headers,
            json={"idempotency_key": "ocr", "use_ocr": True},
        )
        assert response.json()["code"] == "OCR_NOT_CONFIGURED"
        assert (
            client.post(
                "/v0/ocr",
                headers=headers,
                json={"path": str(path), "model_grant_id": "fake", "idempotency_key": "bad"},
            ).status_code
            == 400
        )
        diagnostics = client.get(f"/v0/documents/{version}/parse-diagnostics", headers=headers)
        assert diagnostics.status_code == 200 and diagnostics.json()["runs"] == []


def test_parse_worker_cancellation_kills_owned_process_and_preserves_old_chunks(
    tmp_path, monkeypatch
):
    root = tmp_path / "cancel"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "pdf"
    )["doc_version_id"]
    parser = Parser(db, root)
    parser.parse(version, "initial")
    sources = Sources(db, root)
    anchor = sources.anchor(sources.search("BERT", [version], 1)[0]["source_anchor_id"])
    jobs = Jobs(db)
    queued = parser.parse(version, "cancel-me", queue_only=True)
    import ragsystem.parsing.pipeline as pipeline_module

    original_worker = pipeline_module.run_worker

    def cancel_in_live_worker(*args, **kwargs):
        original_check = kwargs["check"]
        cancelled = False

        def check():
            nonlocal cancelled
            if not cancelled:
                jobs.cancel(queued["id"])
                cancelled = True
            original_check()

        kwargs["check"] = check
        return original_worker(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "run_worker", cancel_in_live_worker)
    with pytest.raises(EngineError, match="LEASE_LOST"):
        parser.parse(version, "cancel-me")
    assert jobs.get(queued["id"])["status"] == "cancelled"
    assert sources.anchor(anchor["source_anchor_id"]) == anchor
    assert list((root / "data/parse-worker-logs").glob("*.stderr.log"))


def test_real_blank_oversized_and_excess_ocr_pages_remain_partial(tmp_path, ocr_directory):
    import pypdfium2 as pdfium
    from ragsystem.parsing.ocr import native_api
    from ragsystem.parsing.process import run_worker

    document = tmp_path / "limits.pdf"
    with pdfium.PdfDocument.new() as pdf:
        # Oversize is rejected before bitmap allocation; no fabricated OCR text.
        pdf.new_page(20000, 20000).close()
        for _ in range(40):
            pdf.new_page(100, 100).close()
        pdf.save(document)
    api, fingerprint = native_api(ocr_directory)
    api.End()
    result = run_worker(
        {
            "pdf_path": str(document),
            "ocr_directory": str(ocr_directory),
            "ocr_fingerprint": fingerprint,
        },
        timeout=30,
    )
    assert len(result["pages"]) == 41
    assert result["pages"][0]["error_code"] == "OCR_PIXEL_LIMIT"
    assert result["pages"][-1]["error_code"] == "OCR_PAGE_LIMIT"
    assert all(not page["text"].strip() and page["error_code"] for page in result["pages"])


def test_cancelled_real_ocr_configuration_does_not_publish(tmp_path, ocr_directory):
    db = Database(tmp_path / "data/research.db")
    jobs = Jobs(db)
    row = jobs.enqueue("verify", "cancel", {"action": "configure_ocr"})
    job = jobs.claim(row["id"])
    jobs.cancel(job["id"])
    service = OcrService(db)
    with pytest.raises(EngineError, match="LEASE_LOST"):
        service.configure(Directories().issue(ocr_directory, "ocr"), job)
    assert not service.status()["configured"] and jobs.get(job["id"])["status"] == "cancelled"
