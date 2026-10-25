"""Two real public papers and one approved model; a Mac component experiment only."""

import hashlib
import importlib.metadata
import json
import platform
import struct
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from ragsystem.indexing.embeddings import Embeddings
from ragsystem.indexing.incremental import embed_visible
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.models.local_onnx import LocalE5
from ragsystem.parsing.pipeline import Parser
from ragsystem.storage.backup import Backups
from ragsystem.storage.database import Database
from ragsystem.vector_adapters.lancedb import LanceDB
from ragsystem.vector_adapters.sqlite_vec import SQLiteVec


def entries_from(db, space, dimension):
    with db.connection() as conn:
        return [
            (row["id"], list(struct.unpack("<" + "f" * dimension, row["vector_bytes"])))
            for row in conn.execute(
                "SELECT * FROM embedding_records WHERE space_id=? ORDER BY id", (space,)
            )
        ]


def main():
    project = Path(__file__).resolve().parents[1]
    model_dir = (
        project
        / ".tools/models/intfloat-multilingual-e5-small-614241f622f53c4eeff9890bdc4f31cfecc418b3"
    )
    encoder = LocalE5(model_dir)
    run_id = str(uuid4())
    root = project / ".tools/test-data" / ("real-vector-ab-" + run_id)
    output = (
        project
        / "docs/engineering/evidence/P0-implementation-2026-10-24"
        / ("real-vector-ab-" + run_id)
    )
    output.mkdir(parents=True)
    db = Database(root / "data/research.db")
    importer, parser = PdfImporter(db, root), Parser(db, root)
    manifest = json.loads((project / "tests/fixtures/public/manifest.json").read_text())
    versions, increments = [], []
    for index, sample in enumerate(manifest):
        source = project / sample["path"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == sample["sha256"]
        version = importer.import_path_for_test(source, sample["sample_id"])[
            "doc_version_id"
        ]
        versions.append(version)
        parser.parse(version, "parse-" + sample["sample_id"])
        before = encoder.encoded_texts
        result = embed_visible(db, encoder)
        result["actual_model_texts_encoded"] = encoder.encoded_texts - before
        result["document_count"] = index + 1
        assert result["actual_model_texts_encoded"] == result["new_embeddings"]
        increments.append(result)
        before = encoder.encoded_texts
        importer.import_path_for_test(source, sample["sample_id"] + "-duplicate")
        repeated = embed_visible(db, encoder)
        assert repeated["new_embeddings"] == 0 and encoder.encoded_texts == before
        increments.append({**repeated, "phase": "duplicate-import-no-reencode"})
    space = increments[0]["space_id"]
    before = encoder.encoded_texts
    reopened = embed_visible(Database(root / "data/research.db"), encoder)
    assert reopened["new_embeddings"] == 0 and before == encoder.encoded_texts
    cache = Embeddings(db)
    entries = entries_from(db, space, encoder.dimension)
    array = np.asarray([v for _, v in entries], dtype=np.float32)
    ids = [i for i, _ in entries]
    np.savez(output / "frozen-vectors.npz", vectors=array, ids=np.array(ids))
    dataset_sha = hashlib.sha256(
        (output / "frozen-vectors.npz").read_bytes()
    ).hexdigest()
    query_texts = [
        "How does BERT pre-training work?",
        "How is dense passage retrieval trained?",
        "如何检索相关的英文论文段落？",
    ]
    query_vectors, embedding_ms = [], []
    for text in query_texts:
        started = time.perf_counter_ns()
        query_vectors.append(encoder.encode([text], query=True)[0])
        embedding_ms.append((time.perf_counter_ns() - started) / 1e6)
    queries = [
        {
            "query_id": f"q{i + 1}",
            "text": text,
            "vector": vector,
            "versions": versions if i != 1 else [versions[-1]],
            "query_embedding_ms": elapsed,
        }
        for i, (text, vector, elapsed) in enumerate(
            zip(query_texts, query_vectors, embedding_ms, strict=True)
        )
    ]
    (output / "frozen-queries.json").write_text(
        json.dumps(queries, ensure_ascii=False, indent=2) + "\n"
    )
    raw, summaries = [], []
    for name, cls, relative in [
        ("sqlite-vec", SQLiteVec, "sqlite-vec/index.db"),
        ("lancedb", LanceDB, "lancedb"),
    ]:
        adapter = cls(root / relative, space, encoder.dimension)
        start = time.perf_counter_ns()
        adapter.upsert(entries)
        upsert_ms = (time.perf_counter_ns() - start) / 1e6
        assert adapter.check_integrity(ids)["ok"]
        for query in queries:
            eligible = cache.eligible(space, query["versions"])
            eligible_entries = [(i, v) for i, v in entries if i in eligible]
            matrix = np.asarray([v for _, v in eligible_entries], dtype=np.float32)
            q = np.asarray(query["vector"], dtype=np.float32)
            distances = 1 - (matrix @ q) / (
                np.linalg.norm(matrix, axis=1) * np.linalg.norm(q)
            )
            oracle = sorted(
                zip([i for i, _ in eligible_entries], distances, strict=True),
                key=lambda row: (float(row[1]), row[0]),
            )[:5]
            for _ in range(2):
                adapter.search_exact(query["vector"], eligible, 5)
            for iteration in range(5):
                start = time.perf_counter_ns()
                hits = adapter.search_exact(query["vector"], eligible, 5)
                elapsed = (time.perf_counter_ns() - start) / 1e6
                correct = [h["embedding_id"] for h in hits] == [i for i, _ in oracle]
                assert correct, (name, query["query_id"], "exact ID mismatch")
                assert np.allclose(
                    [h["distance"] for h in hits], [d for _, d in oracle], atol=1e-5
                )
                raw.append(
                    {
                        "backend": name,
                        "query_id": query["query_id"],
                        "iteration": iteration,
                        "eligible_vectors": len(eligible),
                        "scope_sha256": hashlib.sha256(
                            json.dumps(sorted(eligible)).encode()
                        ).hexdigest(),
                        "component": "adapter_exact_including_validation_and_filter",
                        "latency_ms": elapsed,
                        "engineering_exact_correct": correct,
                        "results": hits,
                    }
                )
        assert adapter.check_integrity(ids)["ok"]
        # Derivation can be rebuilt from persistent raw vectors, without encoder calls.
        before = encoder.encoded_texts
        assert adapter.rebuild(entries)["ok"]
        assert encoder.encoded_texts == before
        times = [row["latency_ms"] for row in raw if row["backend"] == name]
        summaries.append(
            {
                "backend": name,
                "version": importlib.metadata.version(name),
                "p50_ms": float(np.percentile(times, 50)),
                "p95_ms": float(np.percentile(times, 95)),
                "n": len(times),
                "percentile_method": "numpy linear",
                "upsert_ms": upsert_ms,
                "on_disk_bytes": sum(
                    p.stat().st_size
                    for p in (root / relative).parent.rglob("*")
                    if p.is_file()
                )
                if name == "sqlite-vec"
                else sum(
                    p.stat().st_size
                    for p in (root / relative).rglob("*")
                    if p.is_file()
                ),
            }
        )
    backup = Backups(db, root).create(root / "backups")
    restored = root / "restored"
    Backups.restore(backup, restored)
    restored_db = Database(restored / "data/research.db")
    assert entries_from(restored_db, space, encoder.dimension) == entries
    ram_bytes = (
        int(subprocess.check_output(["/usr/sbin/sysctl", "-n", "hw.memsize"]))
        if platform.system() == "Darwin"
        else None
    )
    result = {
        "run_id": run_id,
        "recorded_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "ram_bytes": ram_bytes,
        "ram_source": "sysctl hw.memsize" if ram_bytes else "NOT MEASURED",
        "document_count": len(manifest),
        "vector_count": len(entries),
        "dimension": encoder.dimension,
        "model_fingerprint": encoder.fingerprint,
        "dataset_sha256": dataset_sha,
        "increments": increments,
        "db_reopen": reopened,
        "summaries": summaries,
        "query_embedding_ms": embedding_ms,
        "restored_embedding_count": len(
            entries_from(restored_db, space, encoder.dimension)
        ),
        "truncated_texts": encoder.truncated_texts,
        "raw": raw,
        "scope": "N=2 Mac engineering component experiment; no human retrieval gold or Windows acceptance",
        "scientific_quality": "NOT EVALUATED",
        "backend_selection": "OPEN",
    }
    (output / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "documents": len(manifest),
                "vectors": len(entries),
                "increments": increments,
                "summaries": summaries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
