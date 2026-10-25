"""Real offline OCR trial of a locally rasterized, licensed BERT PDF page."""

import argparse
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import pypdfium2 as pdfium
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.jobs.repository import Jobs
from ragsystem.library.repository import Library
from ragsystem.parsing.ocr import OcrService
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.database import Database

ROOT = Path(__file__).resolve().parents[1]


def rasterize(source, destination):
    with pdfium.PdfDocument(source) as original, pdfium.PdfDocument.new() as scanned:
        page = original[0]
        width, height = page.get_size()
        bitmap = page.render(scale=200 / 72, grayscale=True)
        new = scanned.new_page(width, height)
        image = pdfium.PdfImage.new(scanned)
        image.set_bitmap(bitmap)
        image.set_matrix(pdfium.PdfMatrix(width, 0, 0, height, 0, 0))
        new.insert_obj(image)
        new.gen_content()
        scanned.save(destination)
        new.close()
        bitmap.close()
        page.close()
    with pdfium.PdfDocument(destination) as check:
        text = check[0].get_textpage()
        assert text.count_chars() == 0
        text.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_directory", type=Path)
    args = parser.parse_args()
    trial_id = str(uuid4())
    root = ROOT / ".tools/test-data" / ("ocr-扫描 空格-" + trial_id)
    root.mkdir(parents=True)
    source = ROOT / "tests/fixtures/public/N19-1423.pdf"
    scan = root / "BERT-page1-image-only.pdf"
    rasterize(source, scan)
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(scan, "scan")["doc_version_id"]
    fast = Parser(db, root).parse(version, "fast")
    before = Library(db).parse_diagnostics(version)
    assert before["needs_ocr_pages"] == [1]
    grant = Directories().issue(args.model_directory.resolve(), "ocr")
    jobs = Jobs(db)
    load = jobs.enqueue("verify", "ocr-load", {"action": "configure_ocr"})
    service = OcrService(db)
    service.configure(grant, jobs.claim(load["id"], lease_seconds=180))
    started = time.perf_counter()
    result = Parser(db, root).parse(version, "ocr", use_ocr=True)
    seconds = time.perf_counter() - started
    after = Library(db).parse_diagnostics(version)
    hits = Sources(db, root).search("BERT", [version], 5)
    assert hits
    anchors = [Sources(db, root).anchor(hit["source_anchor_id"]) for hit in hits]
    assert all(
        anchor["location_level"] == "page_only"
        and anchor["file_sha256"] == hashlib.sha256(scan.read_bytes()).hexdigest()
        for anchor in anchors
    )
    with db.connection() as conn:
        text = "\n".join(
            row[0] for row in conn.execute("SELECT clean_text FROM chunks WHERE visible=1")
        )
    record = {
        "trial_id": trial_id,
        "sample": "local rasterization of licensed BERT page 1; not human scientific gold",
        "original_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "original_page": 1,
        "raster_dpi": 200,
        "scan_sha256": hashlib.sha256(scan.read_bytes()).hexdigest(),
        "fast_job": fast,
        "before": before,
        "ocr_job": result,
        "after": after,
        "fingerprint": service.status()["fingerprint"],
        "wall_seconds": seconds,
        "text": text,
        "anchors": anchors,
        "root": str(root),
        "functional_test": "PASS",
        "ocr_character_accuracy": "NOT EVALUATED",
        "scientific_quality": "BLOCKED",
    }
    target = (
        ROOT
        / "docs/engineering/evidence/continuous-2026-10-24"
        / ("ocr-real-" + trial_id + ".json")
    )
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "record": str(target.relative_to(ROOT)),
                "seconds": seconds,
                "characters": len(text),
                "pages": after["pages"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
