"""Synthetic unit oracles for evaluator mechanics, not human scientific gold."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def evaluator():
    spec = importlib.util.spec_from_file_location(
        "evaluate_scientific_quality", ROOT / "tools/evaluate_scientific_quality.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case():
    # The schema tags/reviewer names below are fictional unit-test inputs only.
    return {
        "id": "fixture",
        "data_kind": "human_gold",
        "category": "numeric_units",
        "question": "synthetic unit-only question",
        "answerable": True,
        "targets": [{"sha256": "a" * 64, "page": 1, "quote": "synthetic"}],
        "expected_facts": [
            {"field": "length", "value": "2", "unit": "mm", "conditions": "test fixture"}
        ],
        "annotation": {"status": "adjudicated", "reviewers": ["fixture-a", "fixture-b"]},
    }


def test_separate_retrieval_citations_units_and_no_model_self_grade():
    module = evaluator()
    gold = case()
    predicted = {
        "status": "completed",
        "retrieved": [{"sha256": "a" * 64, "page": 1}],
        "citations": [{"sha256": "a" * 64, "page": 2, "quote": "wrong"}],
        "facts": [{"field": "length", "value": "2", "unit": "cm", "conditions": "test fixture"}],
        "model_support": "supported",
    }
    value = module.score([gold], {"fixture": predicted}, lambda target: target["page"] == 1)
    assert value["metrics"]["retrieval_recall_at_10"]["value"] == 1
    assert value["metrics"]["citation_validity"]["value"] == 0
    assert value["metrics"]["structured_fact_exactness"]["value"] == 0
    assert value["metrics"]["semantic_support"]["value"] is None
    assert value["metrics"]["fact_correct"]["cases"] == 0


def test_synthetic_or_unreviewed_cases_do_not_become_human_gold():
    module = evaluator()
    gold = case()
    gold["data_kind"] = "synthetic_unit_fixture"
    value = module.score([gold], {}, lambda target: True)
    assert (
        value["scored_cases"] == 0 and value["blocked"][0]["reason"] == "HUMAN_GOLD_NOT_ADJUDICATED"
    )
    gold["data_kind"] = "human_gold"
    gold["annotation"]["reviewers"] = ["fixture-a"]
    assert module.score([gold], {}, lambda target: True)["scored_cases"] == 0


def test_missing_prediction_and_wrong_gold_source_block_independently():
    module = evaluator()
    gold = case()
    assert (
        module.score([gold], {}, lambda target: True)["blocked"][0]["reason"]
        == "PREDICTION_MISSING"
    )
    assert (
        module.score([gold], {}, lambda target: False)["blocked"][0]["reason"]
        == "GOLD_SOURCE_NOT_VERIFIED"
    )


def test_correct_refusal_requires_gold_unanswerability():
    module = evaluator()
    gold = case()
    gold.update(category="insufficient_evidence", answerable=False, targets=[])
    value = module.score([gold], {"fixture": {"status": "refused"}}, lambda target: True)
    assert value["metrics"]["refusal_correct"]["value"] == 1
    assert value["metrics"]["citation_validity"]["value"] is None
