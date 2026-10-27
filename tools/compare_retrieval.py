"""Compare retrieval on one frozen SQLite/index copy. No downloads or remote inference.

Writes only a new explicit output directory and retains the snapshot for reproduction.
Local relevance opinions require --include-local-review and an existing local config.
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from ragsystem.domain.errors import EngineError
from ragsystem.indexing.integrity import checked_path, manifest
from ragsystem.models.generation_service import GenerationService
from ragsystem.retrieval.evaluation import latency_summary, ranking_metrics
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.retrieval.reranking import review_order
from ragsystem.storage.database import Database

STRATEGIES = {"keyword", "fts_only", "vector_exact", "hybrid", "keyword_review", "hybrid_review"}


def mean(values):
    return sum(values) / len(values) if values else None


def case_ready(case):
    return (
        isinstance(case.get("id"), str)
        and bool(case["id"])
        and isinstance(case.get("question"), str)
        and bool(case["question"].strip())
        and 1 <= len(case.get("scope", {}).get("version_ids", [])) <= 1000
    )


def human_labels(case, allowed_chunks):
    annotation = case.get("annotation", {})
    reviewers = annotation.get("reviewers", [])
    if (
        case.get("data_kind") != "human_gold"
        or annotation.get("status") != "adjudicated"
        or not isinstance(reviewers, list)
        or len(set(reviewers)) < 2
        or any(not isinstance(item, str) or not item for item in reviewers)
        or annotation.get("pool_complete") is not True
    ):
        return None
    rows = case.get("relevance", [])
    if not isinstance(rows, list):
        raise ValueError("INVALID_GOLD_LABELS")
    labels = {}
    for row in rows:
        key, grade = row.get("chunk_id"), row.get("grade")
        if (
            key not in allowed_chunks
            or key in labels
            or type(grade) is not int
            or not 0 <= grade <= 3
        ):
            raise ValueError("GOLD_SCOPE_OR_GRADE_INVALID")
        labels[key] = grade
    if not labels and case.get("answerable") is not False:
        return None
    return labels


def compare(workspace, output, cases, strategies, repeats=1, include_local_review=False):
    if not strategies or not set(strategies) <= STRATEGIES or not 1 <= repeats <= 100:
        raise ValueError("INVALID_EXPERIMENT")
    if any(value.endswith("_review") for value in strategies) and not include_local_review:
        raise ValueError("LOCAL_REVIEW_REQUIRES_EXPLICIT_FLAG")
    if len({case.get("id") for case in cases}) != len(cases):
        raise ValueError("DUPLICATE_CASE_ID")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    record = {
        "status": "BLOCKED",
        "scientific_quality": "BLOCKED",
        "rows": [],
        "label_unit": "current SQLite chunk ID",
        "strategies": strategies,
        "cases": cases,
        "scope": "same snapshot/query/scope/k=10/no paper quota; no release gate approval",
    }
    if not cases or not all(case_ready(case) for case in cases):
        record["blockers"] = ["CASES_OR_SCOPES_INCOMPLETE"]
    else:
        source = Path(workspace) / "data/research.db"
        snapshot = output / "workspace-snapshot"
        target = snapshot / "data/research.db"
        target.parent.mkdir(parents=True)
        # Read-only URI: opening the source can neither migrate nor create a user DB.
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(target) as dest:
                src.backup(dest)
        db = Database(target)
        search = HybridSearch(db, snapshot)
        config = search.config()
        index_copy_error = None
        if config and any(value.startswith(("hybrid", "vector")) for value in strategies):
            try:
                index = checked_path(Path(workspace), config["relative_path"])
                if any(p.is_symlink() for p in index.rglob("*")) or manifest(index) != config.get(
                    "index_manifest"
                ):
                    raise EngineError("INDEX_INVALID")
                destination = snapshot / config["relative_path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                if index.is_dir():
                    shutil.copytree(index, destination)
                else:
                    shutil.copy2(index, destination)
            except (EngineError, OSError) as exc:
                index_copy_error = exc.code if isinstance(exc, EngineError) else "INDEX_INVALID"
        generation = GenerationService(db)
        try:
            for case in cases:
                scope = case["scope"]
                with db.connection() as conn:
                    search.sources.require_scope(
                        conn, scope["version_ids"], scope.get("project_id")
                    )
                    placeholders = ",".join("?" for _ in scope["version_ids"])
                    chunks = [
                        dict(row)
                        for row in conn.execute(
                            f"SELECT id,doc_version_id,parse_run_id,content_sha256 FROM chunks WHERE visible=1 AND doc_version_id IN ({placeholders}) ORDER BY id",
                            scope["version_ids"],
                        )
                    ]
                freeze = hashlib.sha256(
                    json.dumps({"scope": scope, "chunks": chunks}, sort_keys=True).encode()
                ).hexdigest()
                labels = human_labels(case, {item["id"] for item in chunks})
                for strategy in strategies:
                    for repeat in range(repeats):
                        row = {
                            "id": case["id"],
                            "strategy": strategy,
                            "repeat": repeat,
                            "scope_fingerprint": freeze,
                            "question": case["question"],
                        }
                        started = time.perf_counter()
                        try:
                            if index_copy_error and strategy.startswith(("hybrid", "vector")):
                                raise EngineError(index_copy_error)
                            result = search.search(
                                case["question"],
                                scope["version_ids"],
                                10,
                                scope.get("project_id"),
                                strategy.removesuffix("_review"),
                                filters=scope.get("filters"),
                            )
                            hits = result["results"]
                            if strategy.endswith("_review") and hits:
                                hits, review = review_order(
                                    generation.require(), case["question"], hits
                                )
                                row["local_review"] = review
                            row.update(
                                status="MEASURED",
                                retrieved=[
                                    {key: value for key, value in hit.items() if key != "preview"}
                                    for hit in hits
                                ],
                                query_embedding_ms=result.get("query_embedding_ms", 0),
                                index_generation=result.get("generation"),
                            )
                            complete = labels is not None and all(
                                hit["chunk_id"] in labels for hit in hits
                            )
                            row["metrics"] = (
                                ranking_metrics(labels, [hit["chunk_id"] for hit in hits])
                                if complete
                                else None
                            )
                            row["gold_status"] = "ADJUDICATED" if complete else "HUMAN_GOLD_MISSING"
                        except EngineError as exc:
                            row.update(status="BLOCKED", error_code=exc.code, metrics=None)
                        row["retrieval_ms"] = (time.perf_counter() - started) * 1000
                        record["rows"].append(row)
        finally:
            if generation.generator is not None:
                generation.generator.close()
        record["status"] = (
            "MEASURED" if all(row["status"] == "MEASURED" for row in record["rows"]) else "BLOCKED"
        )
        record["scientific_quality"] = (
            "SCORED_HUMAN_GOLD"
            if all(row.get("metrics") is not None for row in record["rows"])
            else "BLOCKED"
        )
        record["snapshot_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        record["summary"] = {}
        for strategy in strategies:
            rows = [
                row
                for row in record["rows"]
                if row["strategy"] == strategy and row["status"] == "MEASURED"
            ]
            record["summary"][strategy] = {
                "successful_runs": len(rows),
                "retrieval_ms": latency_summary([row["retrieval_ms"] for row in rows]),
                "metrics": {
                    key: mean(
                        [
                            row["metrics"][key]
                            for row in rows
                            if row["metrics"] is not None and row["metrics"][key] is not None
                        ]
                    )
                    for key in ("recall_at_5", "recall_at_10", "mrr", "ndcg_at_10")
                },
            }
    (output / "retrieval-comparison.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    )
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strategies", default="keyword,vector_exact,hybrid")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--include-local-review", action="store_true")
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    result = compare(
        args.workspace,
        args.output,
        cases,
        args.strategies.split(","),
        args.repeats,
        args.include_local_review,
    )
    print(json.dumps({key: result[key] for key in ("status", "scientific_quality")}))
    return 0 if result["status"] == "MEASURED" else 2


if __name__ == "__main__":
    sys.exit(main())
