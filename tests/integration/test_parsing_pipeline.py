from pathlib import Path

import pypdfium2 as pdfium
import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.database import Database

ROOT = Path(__file__).resolve().parents[2]


def test_blank_pdf_is_partial_without_fabricated_chunks(tmp_path):
    source = tmp_path / "blank.pdf"
    with pdfium.PdfDocument.new() as doc:
        doc.new_page(400, 600)
        doc.save(source)
    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(source, "blank")["doc_version_id"]
    Parser(db, root).parse(version, "parse-blank")
    assert PdfImporter(db, root).list_documents()[0]["parse_status"] == "partial"
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        assert (
            conn.execute("SELECT quality_status FROM elements").fetchone()[0]
            == "needs_ocr_or_review"
        )


def test_bad_pdf_reports_failed_job_and_preserves_original(tmp_path):
    source = tmp_path / "malformed.pdf"
    source.write_bytes(b"%PDF-1.4\nintentionally malformed storage/fault test")
    root = tmp_path / "store"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(source, "bad")["doc_version_id"]
    with pytest.raises(EngineError, match="PDF_EXTRACTION_FAILED"):
        Parser(db, root).parse(version, "parse-bad")
    with db.connection() as conn:
        assert conn.execute("SELECT status FROM parse_runs").fetchone()[0] == "failed"
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0


@pytest.mark.parametrize(
    "sample,word", [("N19-1423", "BERT"), ("2020.emnlp-main.550", "retrieval")]
)
def test_real_licensed_pdf_extraction_and_source_version(tmp_path, sample, word):
    source = ROOT / "tests/fixtures/public" / (sample + ".pdf")
    if not source.is_file():
        pytest.skip("Licensed public PDF has not been obtained")
    root = tmp_path / "真实 论文"
    db = Database(root / "data/research.db")
    importer = PdfImporter(db, root)
    version = importer.import_path_for_test(source, sample)["doc_version_id"]
    parser = Parser(db, root)
    first = parser.parse(version, "parse-" + sample)
    assert first["status"] == "completed"
    assert parser.parse(version, "parse-" + sample)["result_ref"] == first["result_ref"]
    sources = Sources(db, root)
    hits = sources.search(word, [version], 5)
    assert hits and all(hit["doc_version_id"] == version for hit in hits)
    anchor = sources.anchor(hits[0]["source_anchor_id"])
    assert anchor["location_level"] == "page_only"
    assert anchor["bbox_norm"] is None
    assert anchor["file_sha256"] == importer.list_documents()[0]["file_sha256"]
    import json

    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "contracts/source-anchor.schema.json").read_text())
    Draft202012Validator(schema).validate(anchor)
    with pytest.raises(EngineError, match="SCOPE_NOT_AVAILABLE"):
        sources.search(word, ["unauthorized-version"], 5)
    parser.parse(version, "reparse-" + sample)
    with pytest.raises(EngineError, match="NOT_FOUND"):
        sources.anchor(anchor["source_anchor_id"])
    assert db.integrity()["integrity_check"] == ["ok"]
