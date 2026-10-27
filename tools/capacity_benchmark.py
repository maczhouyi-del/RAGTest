"""Progressive real/synthetic corpus workflow. No download, cloud or user-workspace access."""

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import Database

ROOT = Path(__file__).resolve().parents[1]


def synthetic_pdf(path, index):
    text = f"SYNTHETIC CAPACITY FIXTURE ONLY paper {index} unique retrieval keyword item{index:06d} common benchmark evidence. Not a scientific paper or gold answer."
    body = f"BT /F1 9 Tf 20 500 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(body)} >>\nstream\n".encode() + body + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, value in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{n} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(data)
    data.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    path.write_bytes(data)


def vector_digest(db):
    digest = hashlib.sha256()
    with db.connection() as conn:
        for row in conn.execute("SELECT id,vector_bytes FROM embedding_records ORDER BY id"):
            digest.update(row[0].encode())
            digest.update(row[1])
    return digest.hexdigest()


def peak_memory():
    if sys.platform == "win32":
        return {"status": "NOT_MEASURED", "reason": "Windows working-set sampler required"}
    import resource

    factor = 1 if sys.platform == "darwin" else 1024
    return {
        "status": "MEASURED",
        "self_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * factor,
        "child_peak_bytes": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * factor,
        "scope": "separate process high-water marks, NOT simultaneous process-tree total",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["synthetic", "real"], required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--stages", default="10,50,200,1000")
    parser.add_argument("--queries", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.model_directory:
        args.model_directory = args.model_directory.absolute()
    stages = [int(value) for value in args.stages.split(",")]
    assert (
        stages == sorted(set(stages))
        and 1 <= min(stages) <= max(stages) <= 1000
        and 1 <= args.queries <= 100
    )
    args.output.mkdir(parents=True, exist_ok=True)
    root = ROOT / ".tools/test-data" / ("capacity-" + args.kind + "-" + str(uuid4()))
    record = {
        "started_at": datetime.now(UTC).isoformat(),
        "kind": args.kind,
        "status": "IN_PROGRESS",
        "root": str(root),
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "stages": [],
        "scientific_quality": "NOT_EVALUATED",
        "real_capacity_gate": "BLOCKED" if args.kind == "synthetic" else "NOT_EXECUTED",
        "timing_scope": "incremental import/parse/index per stage; warm retrieval separated from measured query embedding; no generation; metadata extraction not run",
    }
    entries = json.loads(args.manifest.read_text()) if args.manifest else []
    if args.kind == "real" and len({entry.get("sha256") for entry in entries}) < max(stages):
        record.update(
            status="BLOCKED",
            real_capacity_gate="BLOCKED",
            reason="not enough distinct licensed SHA-identified papers",
            available=len(entries),
            required=max(stages),
        )
        (args.output / "capacity.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record))
        return 2
    root.mkdir(parents=True)
    db = Database(root / "data/research.db")
    importer = PdfImporter(db, root)
    parser_service = Parser(db, root)
    search = HybridSearch(db, root)
    jobs = Jobs(db)
    inputs = root / "synthetic-input"
    inputs.mkdir()
    if args.kind == "real":
        for item in entries[: max(stages)]:
            assert item.get("license") and item.get("path") and len(item["sha256"]) == 64
            path = Path(item["path"])
            path = path if path.is_absolute() else ROOT / path
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
            item["resolved_path"] = str(path)
    versions = []

    def build(directory, key):
        job = jobs.enqueue("embed_batch", key, {"backend": "sqlite-vec"})
        search.build(job["id"], Directories().issue(directory, "embedding"), "sqlite-vec")
        assert jobs.get(job["id"])["status"] == "completed", jobs.get(job["id"])["error_code"]
        return search.config()

    try:
        for count in stages:
            stage = {
                "documents": count,
                "kind": args.kind,
                "import_seconds": 0.0,
                "parse_seconds": 0.0,
            }
            for index in range(len(versions), count):
                if args.kind == "synthetic":
                    source = inputs / f"synthetic-{index}.pdf"
                    synthetic_pdf(source, index)
                else:
                    source = Path(entries[index]["resolved_path"])
                started = time.perf_counter()
                version = importer.import_path_for_test(source, f"import-{index}")["doc_version_id"]
                stage["import_seconds"] += time.perf_counter() - started
                started = time.perf_counter()
                parser_service.parse(version, f"parse-{index}")
                stage["parse_seconds"] += time.perf_counter() - started
                versions.append(version)
            if args.model_directory:
                started = time.perf_counter()
                config = build(args.model_directory, f"index-{count}")
                stage["index_seconds"] = time.perf_counter() - started
                stage["index_delta"] = {
                    key: config[key] for key in ("new_embeddings", "reused_embeddings", "chunks")
                }
                # Same fingerprint/content, new publication: no new embedding calculation.
                before = vector_digest(db)
                repeat = build(args.model_directory, f"repeat-{count}")
                assert repeat["new_embeddings"] == 0 and vector_digest(db) == before
                stage["unchanged_reindex_new_embeddings"] = 0
                query = "common benchmark" if args.kind == "synthetic" else "pre-training retrieval"
                search.search(query, versions, 5, None, "hybrid")  # separate cold model setup
                elapsed = []
                without_encoding = []
                encoding = []
                for _ in range(args.queries):
                    started = time.perf_counter()
                    answer = search.search(query, versions, 5, None, "hybrid")
                    total = (time.perf_counter() - started) * 1000
                    elapsed.append(total)
                    encoding.append(answer["query_embedding_ms"])
                    without_encoding.append(max(0, total - answer["query_embedding_ms"]))
                stage["retrieval_ms"] = {
                    "samples": args.queries,
                    "warm_total_p50": sorted(elapsed)[len(elapsed) // 2],
                    "warm_total_p95": sorted(elapsed)[math.ceil(0.95 * len(elapsed)) - 1],
                    "excluding_measured_encoding_p95": sorted(without_encoding)[
                        math.ceil(0.95 * len(without_encoding)) - 1
                    ],
                    "query_encoding_mean": sum(encoding) / len(encoding),
                    "generation_included": False,
                    "SLA_acceptance": "NOT_EVALUATED",
                }
            else:
                stage["index_status"] = "NOT_EXECUTED: explicit approved model directory required"
            with db.connection() as conn:
                stage.update(
                    pages=conn.execute(
                        "SELECT sum(page_count) FROM parse_runs WHERE status IN ('ready','partial')"
                    ).fetchone()[0],
                    chunks=conn.execute("SELECT count(*) FROM chunks WHERE visible=1").fetchone()[
                        0
                    ],
                    vectors=conn.execute("SELECT count(*) FROM embedding_records").fetchone()[0],
                    pdf_bytes=sum(
                        row[0] for row in conn.execute("SELECT size_bytes FROM file_assets")
                    ),
                )
            assert type(stage["pages"]) is int and stage["pages"] >= count
            before = vector_digest(db)
            started = time.perf_counter()
            snapshot = Backups(db, root).create(root / "backups")
            stage["backup_seconds"] = time.perf_counter() - started
            target = root / f"restored-{count}"
            started = time.perf_counter()
            Backups.restore(snapshot, target)
            stage["restore_seconds"] = time.perf_counter() - started
            restored = Database(target / "data/research.db")
            assert (
                restored.integrity()["integrity_check"] == ["ok"]
                and vector_digest(restored) == before
            )
            if args.model_directory:
                rebuilt = HybridSearch(restored, target)
                restore_job = Jobs(restored).enqueue("embed_batch", f"restore-{count}", {})
                rebuilt.build(
                    restore_job["id"],
                    Directories().issue(args.model_directory, "embedding"),
                    "sqlite-vec",
                )
                assert (
                    rebuilt.config()["new_embeddings"] == 0
                    and rebuilt.config()["reused_embeddings"] == stage["vectors"]
                )
                stage["restore_rebuild_new_embeddings"] = 0
            stage["disk_bytes_with_retained_backups"] = sum(
                path.stat().st_size for path in root.rglob("*") if path.is_file()
            )
            stage["memory"] = peak_memory()
            stage["status"] = "PASS"
            record["stages"].append(stage)
            (args.output / "capacity.json").write_text(json.dumps(record, indent=2) + "\n")
            print(json.dumps(stage), flush=True)
        record["status"] = "PASS"
        record["real_capacity_gate"] = (
            "BLOCKED: synthetic corpus cannot qualify real capacity"
            if args.kind == "synthetic"
            else "REQUIRES_REVIEW"
        )
    except Exception as exc:
        record.update(status="FAIL", error_code=getattr(exc, "code", type(exc).__name__))
    finally:
        record["finished_at"] = datetime.now(UTC).isoformat()
        (args.output / "capacity.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": record["status"],
                "error_code": record.get("error_code"),
                "stages_completed": len(record["stages"]),
            }
        ),
        flush=True,
    )
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
