"""Fixed, optional local layout/table candidates. No downloads or remote services."""

import hashlib
import importlib.metadata
import json
import os
from contextlib import closing
from pathlib import Path

from ragsystem.domain.errors import EngineError
from ragsystem.ipc.directories import directory_identity
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.process import run_worker
from ragsystem.storage.database import utc_now

LAYOUT_REVISION = "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"
TABLE_REVISION = "2199320848bb9a8a519d22e4b528185a4f9a6f64"
WEIGHTS = {
    "docling-project--docling-layout-heron/config.json": (
        3268,
        "fdea30805ce2f5666b147fca941dcdd27ad468e27d6ed21902207d3da056a97d",
    ),
    "docling-project--docling-layout-heron/preprocessor_config.json": (
        444,
        "cd38cd59999e7a95d68e487fbe5132df3d4e5c32a0836add57e6126ba0c4eaf1",
    ),
    "docling-project--docling-layout-heron/model.safetensors": (
        171658996,
        "00333a43451945aaf89db8ca9c0a17e75d1537c17db60fdb91aa95f4c7929e0c",
    ),
    "docling-project--docling-models/model_artifacts/tableformer/fast/tm_config.json": (
        7060,
        "dca6762508dddfae6d57d6cb4ef822c6000119dff0f3b6489db7413118c2622a",
    ),
    "docling-project--docling-models/model_artifacts/tableformer/fast/tableformer_fast.safetensors": (
        145453276,
        "3119563aab5a7c96fda4d621119b63fd8806272b86c30936d15507616422f718",
    ),
}
POLICY = {
    "pipeline": "docling-local-layout-table-candidate-v1",
    "layout_revision": LAYOUT_REVISION,
    "table_revision": TABLE_REVISION,
    "weight_sha256": {name: value[1] for name, value in WEIGHTS.items()},
    "device": "cpu",
    "threads": 2,
    "max_pages": 40,
    "max_page_pixels_at_144dpi": 8000000,
    "max_cells": 10000,
    "max_tables": 200,
    "ocr": False,
    "enrichment": False,
    "table_mode": "fast",
    "location_level": "page_only",
    "cell_review": "unreviewed",
    "serialization": "ordered-text-and-tab-separated-cells-codepoints-v1",
    "pdf_backend": "pdfium-glyph-words-v1",
}
RUNTIMES = (
    "docling-slim",
    "docling-core",
    "docling-ibm-models",
    "torch",
    "torchvision",
    "transformers",
    "safetensors",
    "opencv-python-headless",
    "pypdfium2",
)


def verify_directory(directory):
    path = Path(directory)
    directory_identity(path)
    for name, (size, expected) in WEIGHTS.items():
        file = path / name
        directory_identity(file.parent)
        if file.is_symlink() or not file.is_file() or file.stat().st_size != size:
            raise EngineError("DOCLING_MODEL_NOT_AVAILABLE")
        with file.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise EngineError("DOCLING_MODEL_HASH_MISMATCH")
    return path


def runtime_fingerprint():
    try:
        versions = {name: importlib.metadata.version(name) for name in RUNTIMES}
    except importlib.metadata.PackageNotFoundError as exc:
        raise EngineError("DOCLING_RUNTIME_NOT_PACKAGED") from exc
    return {**POLICY, "runtimes": versions}


def create_pipeline(directory):
    directory = verify_directory(directory)
    fingerprint = runtime_fingerprint()
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        os.environ[key] = "1"
    try:
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.pipeline_options import TableFormerMode, ThreadedPdfPipelineOptions
        from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    except (ImportError, OSError) as exc:
        raise EngineError("DOCLING_RUNTIME_NOT_PACKAGED") from exc
    options = ThreadedPdfPipelineOptions(
        artifacts_path=directory,
        do_ocr=False,
        do_table_structure=True,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        do_picture_classification=False,
        do_picture_description=False,
        do_chart_extraction=False,
        extract_form_fields=False,
        generate_page_images=False,
        generate_picture_images=False,
        generate_table_images=False,
        enable_remote_services=False,
        allow_external_plugins=False,
        accelerator_options=AcceleratorOptions(device="cpu", num_threads=2),
        document_timeout=240,
        layout_batch_size=1,
        table_batch_size=1,
        ocr_batch_size=1,
        queue_max_size=2,
    )
    options.layout_options.model_spec.revision = LAYOUT_REVISION
    options.layout_options.engine_options.compile_model = False
    options.table_structure_options.mode = TableFormerMode.FAST
    return StandardPdfPipeline(options), fingerprint


def serialize_document(document, page_count, rotations):
    """Preserve model provenance. Never invent a page for a multi-page item/cell."""
    pages = [
        {
            "page_number": i + 1,
            "text": "",
            "error_code": None,
            "rotation": rotations[i],
            "method": "docling",
            "blocks": [],
        }
        for i in range(page_count)
    ]
    tables, cell_count, unresolved_items, unlocated_items = [], 0, 0, []
    for item, _ in document.iterate_items():
        raw = item.model_dump(mode="json", exclude_none=True)
        prov = raw.get("prov", [])
        numbers = sorted({p["page_no"] for p in prov})
        if any(type(n) is not int or not 1 <= n <= page_count for n in numbers):
            raise EngineError("DOCLING_STRUCTURE_INVALID")
        page = pages[numbers[0] - 1] if len(numbers) == 1 else None
        is_table = raw.get("label") == "table"
        if is_table:
            data = raw["data"]
            rows, cols = data["num_rows"], data["num_cols"]
            cells = data["table_cells"]
            cell_count += len(cells)
            if not (0 <= rows <= 1000 and 0 <= cols <= 100):
                raise EngineError("DOCLING_STRUCTURE_LIMIT")
            if cell_count > POLICY["max_cells"] or len(tables) >= POLICY["max_tables"]:
                raise EngineError("DOCLING_STRUCTURE_LIMIT")
            table = {
                "source_ref": raw["self_ref"],
                "page_number": page["page_number"] if page else None,
                "source_pages": numbers,
                "rows": rows,
                "columns": cols,
                "raw": raw,
                "cells": [],
            }
            # Only real cell text is indexed; row/column IDs are separate metadata.
            ordered = sorted(
                cells, key=lambda c: (c["start_row_offset_idx"], c["start_col_offset_idx"])
            )
            for cell in ordered:
                r, c = cell["start_row_offset_idx"], cell["start_col_offset_idx"]
                re, ce = cell["end_row_offset_idx"], cell["end_col_offset_idx"]
                if not (0 <= r < re <= rows and 0 <= c < ce <= cols) or len(cell["text"]) > 20000:
                    raise EngineError("DOCLING_STRUCTURE_INVALID")
                table["cells"].append(
                    {
                        "row": r,
                        "column": c,
                        "row_end": re,
                        "column_end": ce,
                        "text": cell["text"],
                        "column_header": cell.get("column_header", False),
                        "row_header": cell.get("row_header", False),
                        "raw": cell,
                        "start": None,
                        "end": None,
                    }
                )
            tables.append(table)
        if page is None:
            # Docling may join a paragraph across pages. Use only a complete,
            # non-overlapping charspan partition; never guess by fuzzy matching.
            text = raw.get("text", "")
            spans = sorted(prov, key=lambda p: p.get("charspan", [-1])[0])
            cursor, valid = 0, bool(text) and not is_table
            for source in spans:
                a, b = source.get("charspan", (-1, -1))
                if (
                    type(a) is not int
                    or type(b) is not int
                    or a != cursor
                    or not a < b <= len(text)
                ):
                    valid = False
                    break
                cursor = b
            if valid and cursor == len(text):
                for source in spans:
                    target = pages[source["page_no"] - 1]
                    a, b = source["charspan"]
                    start = len(target["text"])
                    target["text"] += text[a:b]
                    target["blocks"].append(
                        {
                            "source_ref": raw["self_ref"],
                            "label": raw.get("label"),
                            "start": start,
                            "end": len(target["text"]),
                            "item_charspan": [a, b],
                            "provenance": [source],
                            "raw_item": raw,
                        }
                    )
                    target["text"] += "\n"
                    if len(target["text"]) > 50000:
                        raise EngineError("PAGE_TEXT_LIMIT")
                continue
            unresolved_items += 1
            if not numbers:
                unlocated_items.append(raw)
            for number in numbers:
                pages[number - 1]["error_code"] = "DOCLING_ITEM_LOCATION_UNRESOLVED"
                pages[number - 1]["blocks"].append(
                    {"source_ref": raw["self_ref"], "unresolved": True, "raw_item": raw}
                )
            continue
        start = len(page["text"])
        if is_table:
            previous_row, previous_col = None, 0
            for cell in table["cells"]:
                if previous_row != cell["row"]:
                    if previous_row is not None:
                        page["text"] += "\n"
                    previous_col = 0
                else:
                    page["text"] += "\t"
                page["text"] += "\t" * max(0, cell["column"] - previous_col)
                cell["start"] = len(page["text"])
                page["text"] += cell["text"]
                cell["end"] = len(page["text"])
                previous_row, previous_col = cell["row"], cell["column_end"]
        else:
            page["text"] += raw.get("text", "")
        end = len(page["text"])
        if end > start:
            page["blocks"].append(
                {
                    "source_ref": raw["self_ref"],
                    "label": raw.get("label"),
                    "start": start,
                    "end": end,
                    "provenance": prov,
                    "raw_item": raw,
                }
            )
            page["text"] += "\n"
        if len(page["text"]) > 50000:
            raise EngineError("PAGE_TEXT_LIMIT")
    if sum(len(p["text"]) for p in pages) > 1500000:
        raise EngineError("DOCUMENT_TEXT_LIMIT")
    return {
        "parser": "docling",
        "pages": pages,
        "tables": tables,
        "unresolved_items": unresolved_items,
        "unlocated_items": unlocated_items,
    }


def parse_document(directory, path, expected_fingerprint, page_numbers=None):
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(path) as pdf:
        from ragsystem.parsing.publication import validate_selection

        selection = validate_selection(page_numbers)
        if not 0 < len(pdf) <= 500 or (selection is None and len(pdf) > POLICY["max_pages"]):
            raise EngineError("DOCLING_PAGE_LIMIT")
        if selection is not None and max(selection) > len(pdf):
            raise EngineError("SOURCE_PAGE_INVALID")
        selected = selection or list(range(1, len(pdf) + 1))
        rotations = [0] * len(pdf)
        for number in selected:
            i = number - 1
            with closing(pdf[i]) as page:
                width, height = page.get_size()
                if (
                    width <= 0
                    or height <= 0
                    or width * height * 4 > POLICY["max_page_pixels_at_144dpi"]
                ):
                    raise EngineError("DOCLING_PIXEL_LIMIT")
                rotations[i] = page.get_rotation()
                with closing(page.get_textpage()) as textpage:
                    if textpage.count_chars() > 50000:
                        raise EngineError("PAGE_TEXT_LIMIT")
    pipeline, fingerprint = create_pipeline(directory)
    if fingerprint != expected_fingerprint:
        raise EngineError("DOCLING_FINGERPRINT_CHANGED")
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import InputDocument
    from docling.datamodel.settings import DocumentLimits

    from ragsystem.parsing.docling_backend import WordDocumentBackend

    groups = []
    for number in selected:
        if groups and number == groups[-1][-1] + 1:
            groups[-1].append(number)
        else:
            groups.append([number])
    output = {
        "parser": "docling",
        "document_page_count": len(rotations),
        "pages": [],
        "tables": [],
        "unresolved_items": 0,
        "unlocated_items": [],
    }
    for group in groups:
        doc = InputDocument(
            Path(path),
            InputFormat.PDF,
            WordDocumentBackend,
            limits=DocumentLimits(
                max_num_pages=500, max_file_size=64 * 1024 * 1024, page_range=(group[0], group[-1])
            ),
        )
        if not doc.valid:
            raise EngineError("DOCLING_INPUT_INVALID")
        result = pipeline.execute(doc, raises_on_error=True)
        if result.status.value != "success":
            raise EngineError("DOCLING_CONVERSION_INCOMPLETE")
        content = serialize_document(result.document, len(rotations), rotations)
        for table in content["tables"]:
            if set(table["source_pages"]) - set(group):
                raise EngineError("DOCLING_STRUCTURE_INVALID")
        output["pages"].extend(p for p in content["pages"] if p["page_number"] in group)
        output["tables"].extend(content["tables"])
        output["unresolved_items"] += content["unresolved_items"]
        output["unlocated_items"].extend(content["unlocated_items"])
        if (
            len(output["tables"]) > POLICY["max_tables"]
            or sum(len(t["cells"]) for t in output["tables"]) > POLICY["max_cells"]
        ):
            raise EngineError("DOCLING_STRUCTURE_LIMIT")
        if sum(len(p["text"]) for p in output["pages"]) > 1500000:
            raise EngineError("DOCUMENT_TEXT_LIMIT")
    return output


class DoclingService:
    def __init__(self, db):
        self.db = db

    def status(self):
        with self.db.connection() as conn:
            row = conn.execute("SELECT value_json FROM app_settings WHERE key='docling'").fetchone()
        config = json.loads(row[0]) if row else None
        return {
            "configured": bool(config),
            "fingerprint": config["fingerprint"] if config else None,
            "candidate_only": True,
        }

    def require(self):
        with self.db.connection() as conn:
            row = conn.execute("SELECT value_json FROM app_settings WHERE key='docling'").fetchone()
        if not row:
            raise EngineError("DOCLING_NOT_CONFIGURED")
        config = json.loads(row[0])
        verify_directory(config["directory"])
        if runtime_fingerprint() != config["fingerprint"]:
            raise EngineError("DOCLING_FINGERPRINT_CHANGED")
        return config

    def configure(self, grant, job):
        grant.check()
        verify_directory(grant.path)
        jobs = Jobs(self.db)

        def check():
            with self.db.connection() as conn:
                jobs.require_lease(conn, job["id"], job["lease_token"])

        result = run_worker(
            {"operation": "docling_probe", "docling_directory": str(grant.path)},
            timeout=120,
            check=check,
            log_directory=self.db.path.parent / "parse-worker-logs",
        )
        grant.check()
        config = {"directory": str(grant.path), "fingerprint": result["docling_fingerprint"]}
        with self.db.transaction() as conn:
            jobs.require_lease(conn, job["id"], job["lease_token"])
            conn.execute(
                "INSERT INTO app_settings VALUES('docling',?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                (json.dumps(config), utc_now()),
            )
            jobs.complete(
                job["id"], job["lease_token"], "docling:approved-candidates", connection=conn
            )
        return self.status()
