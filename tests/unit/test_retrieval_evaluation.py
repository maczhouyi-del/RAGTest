"""Fictional metric oracles only; none of these labels are scientific gold."""

import importlib.util
import math
from pathlib import Path

import pytest
from ragsystem.retrieval.evaluation import latency_summary, ranking_metrics


def comparison_tool():
    spec = importlib.util.spec_from_file_location(
        "compare_retrieval", Path(__file__).resolve().parents[2] / "tools/compare_retrieval.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ranking_metric_oracle_duplicate_ids_missing_gold_and_rank_cutoff():
    result = ranking_metrics({"a": 3, "b": 1}, ["x", "a", "a", "z", "q", "b"])
    assert result["recall_at_5"] == 0.5 and result["recall_at_10"] == 1
    assert result["mrr"] == 0.5
    assert result["ndcg_at_10"] == pytest.approx(
        (7 / math.log2(3) + 1 / math.log2(7)) / (7 + 1 / math.log2(3))
    )
    assert ranking_metrics({"a": 1}, ["x"])["mrr"] == 0
    assert ranking_metrics({}, ["a"])["recall_at_5"] is None
    with pytest.raises(ValueError, match="INVALID_RELEVANCE_GRADE"):
        ranking_metrics({"a": True}, ["a"])


def test_latency_percentiles_are_nearest_rank_p95_and_median_p50():
    assert latency_summary(list(range(1, 101))) == {"samples": 100, "p50": 50.5, "p95": 95}
    assert latency_summary([])["p95"] is None
    for value in (-1, float("inf"), True):
        with pytest.raises(ValueError, match="INVALID_LATENCY"):
            latency_summary([value])


def test_unreviewed_incomplete_out_of_scope_or_duplicate_labels_cannot_score():
    module = comparison_tool()
    assert module.human_labels({"relevance": [{"chunk_id": "a", "grade": 3}]}, {"a"}) is None
    case = {
        "data_kind": "human_gold",
        "relevance": [{"chunk_id": "a", "grade": 3}],
        "annotation": {
            "status": "adjudicated",
            "reviewers": ["fixture-a", "fixture-b"],
            "pool_complete": False,
        },
    }
    assert module.human_labels(case, {"a"}) is None
    case["annotation"]["pool_complete"] = True
    assert module.human_labels(case, {"a"}) == {"a": 3}
    with pytest.raises(ValueError, match="GOLD_SCOPE_OR_GRADE_INVALID"):
        module.human_labels(case, {"b"})
    case["relevance"].append({"chunk_id": "a", "grade": 2})
    with pytest.raises(ValueError, match="GOLD_SCOPE_OR_GRADE_INVALID"):
        module.human_labels(case, {"a"})


def test_empty_template_is_blocked_before_accessing_workspace(tmp_path):
    module = comparison_tool()
    result = module.compare(tmp_path / "does-not-exist", tmp_path / "output", [], ["keyword"])
    assert result["status"] == "BLOCKED" and result["rows"] == []
    assert result["blockers"] == ["CASES_OR_SCOPES_INCOMPLETE"]
    with pytest.raises(ValueError, match="LOCAL_REVIEW_REQUIRES_EXPLICIT_FLAG"):
        module.compare(tmp_path / "absent", tmp_path / "no-model-call", [], ["keyword_review"])
