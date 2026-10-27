"""Real retrieval execution, synthetic questions/labels; no scientific quality claim."""

import importlib.util
import json
import os
import sqlite3
from pathlib import Path

import pytest
from ragsystem.ipc.directories import Directories
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from test_mvp_core import ROOT, store


def module():
    spec = importlib.util.spec_from_file_location(
        "compare_retrieval", ROOT / "tools/compare_retrieval.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def cases(version):
    return [
        {
            "id": "engineering-sample",
            "data_kind": "real_pdf_unreviewed_query",
            "question": "BERT pre-training tasks",
            "scope": {"version_ids": [version], "project_id": None},
            "annotation": {"status": "unreviewed", "reviewers": []},
        }
    ]


def test_comparison_retains_original_sqlite_and_does_not_invent_gold(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    with sqlite3.connect(db.path) as conn:
        before = "\n".join(conn.iterdump())
    result = module().compare(
        root, tmp_path / "comparison", cases(version), ["keyword", "fts_only"], 2
    )
    assert result["status"] == "MEASURED" and result["scientific_quality"] == "BLOCKED"
    assert len({row["scope_fingerprint"] for row in result["rows"]}) == 1
    assert all(
        row["metrics"] is None and row["gold_status"] == "HUMAN_GOLD_MISSING"
        for row in result["rows"]
    )
    assert all(row["retrieval_ms"] > 0 for row in result["rows"])
    with sqlite3.connect(db.path) as conn:
        assert "\n".join(conn.iterdump()) == before
    assert (tmp_path / "comparison/workspace-snapshot/data/research.db").is_file()


@pytest.mark.skipif(
    not os.environ.get("RAGSYSTEM_MODEL_DIR"), reason="existing approved E5 required"
)
def test_real_e5_same_snapshot_strategy_comparison_and_cross_language_execution(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    search = HybridSearch(db, root)
    job = Jobs(db).enqueue("embed_batch", "comparison-index", {})
    search.build(
        job["id"],
        Directories().issue(Path(os.environ["RAGSYSTEM_MODEL_DIR"]), "embedding"),
        "sqlite-vec",
    )
    assert Jobs(db).get(job["id"])["status"] == "completed"
    query_cases = cases(version)
    query_cases.append(
        {
            **query_cases[0],
            "id": "cross-language-unreviewed",
            "question": "掩码语言预测和句子关系预训练",
        }
    )
    result = module().compare(
        root, tmp_path / "real-comparison", query_cases, ["keyword", "vector_exact", "hybrid"], 2
    )
    assert result["status"] == "MEASURED" and result["scientific_quality"] == "BLOCKED"
    assert len(result["rows"]) == 12
    assert all(row["metrics"] is None for row in result["rows"])
    semantic = [
        row
        for row in result["rows"]
        if row["id"] == "cross-language-unreviewed" and row["strategy"] == "vector_exact"
    ]
    assert all(row["retrieved"] and row["query_embedding_ms"] > 0 for row in semantic)
    # Explicitly retain this actual small experiment when requested; no PDF upload.
    output = os.environ.get("RAGSYSTEM_COMPARISON_EVIDENCE")
    if output:
        Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
