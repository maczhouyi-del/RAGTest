"""Real licensed PDF engineering smoke, explicitly not a scientific gold evaluation."""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import Database


def main():
    project = Path(__file__).resolve().parents[1]
    fixture = project / "tests/fixtures/public/manifest.json"
    manifest = json.loads(fixture.read_text())
    root = project / ".tools/test-data" / ("public-smoke-" + str(uuid4()))
    db = Database(root / "data/research.db")
    importer, parser = PdfImporter(db, root), Parser(db, root)
    sources = Sources(db, root)
    records = []
    for sample in manifest:
        pdf = project / sample["path"]
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == sample["sha256"]
        document = importer.import_path_for_test(pdf, sample["sample_id"])
        duplicate = importer.import_path_for_test(
            pdf, sample["sample_id"] + "-duplicate"
        )
        assert document == duplicate
        job = parser.parse(document["doc_version_id"], "parse-" + sample["sample_id"])
        query = "BERT" if sample["sample_id"] == "N19-1423" else "retrieval"
        hits = sources.search(query, [document["doc_version_id"]], 5)
        assert hits
        anchor = sources.anchor(hits[0]["source_anchor_id"])
        assert anchor["file_sha256"] == sample["sha256"]
        with db.connection() as conn:
            run_id = job["result_ref"].split(":", 1)[1]
            run = dict(
                conn.execute(
                    "SELECT * FROM parse_runs WHERE id=?", (run_id,)
                ).fetchone()
            )
            chunks = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE parse_run_id=?", (run_id,)
            ).fetchone()[0]
        records.append(
            {
                "sample_id": sample["sample_id"],
                "file_sha256": sample["sha256"],
                "pages": run["page_count"],
                "status": run["status"],
                "chunks": chunks,
                "query": query,
                "hit_count": len(hits),
                "anchor": anchor,
            }
        )
    backup = Backups(db, root).create(root / "backups")
    restored = root / "restored"
    Backups.restore(backup, restored)
    integrity = Database(restored / "data/research.db").integrity()
    assert integrity == {"integrity_check": ["ok"], "foreign_key_check": []}
    result = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "test_root": str(root),
        "records": records,
        "document_count": len(importer.list_documents()),
        "restored_integrity": integrity,
        "scientific_quality": "BLOCKED: no human gold labels",
        "model_used": False,
        "windows_tested": False,
    }
    output = (
        project
        / "docs/engineering/evidence/P0-implementation-2026-10-24/public-corpus-smoke.json"
    )
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "document_count": result["document_count"],
                "samples": [
                    {k: r[k] for k in ["sample_id", "pages", "chunks", "status"]}
                    for r in records
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
