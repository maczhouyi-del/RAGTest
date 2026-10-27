"""Offline scoring against human annotations. Never calls a model or invents gold."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from ragsystem.domain.errors import EngineError
from ragsystem.parsing.process import run_worker
from ragsystem.retrieval.evaluation import latency_summary, ranking_metrics

ROOT = Path(__file__).resolve().parents[1]

CATEGORIES = {
    "methods",
    "results",
    "numeric_units",
    "tables",
    "cross_document",
    "multi_turn",
    "insufficient_evidence",
}


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def reviewed(value):
    return (
        value.get("status") == "adjudicated"
        and isinstance(value.get("reviewers"), list)
        and all(isinstance(item, str) and item for item in value["reviewers"])
        and len(set(value["reviewers"])) >= 2
    )


def average(values):
    return sum(values) / len(values) if values else None


def score(cases, predictions, verify_source):
    observations = []
    blocked = []
    for gold in cases:
        identifier = gold.get("id", "")
        if gold.get("data_kind") != "human_gold" or not reviewed(gold.get("annotation", {})):
            blocked.append({"id": identifier, "reason": "HUMAN_GOLD_NOT_ADJUDICATED"})
            continue
        if gold.get("category") not in CATEGORIES:
            raise ValueError("INVALID_CATEGORY")
        targets = gold["targets"]
        if not all(verify_source(item) for item in targets):
            blocked.append({"id": identifier, "reason": "GOLD_SOURCE_NOT_VERIFIED"})
            continue
        prediction = predictions.get(identifier)
        if prediction is None:
            blocked.append({"id": identifier, "reason": "PREDICTION_MISSING"})
            continue
        required = {(item["sha256"], item["page"]) for item in targets}
        ranked = [(item["sha256"], item["page"]) for item in prediction.get("retrieved", [])[:10]]
        citations = prediction.get("citations", [])
        judgment = prediction.get("human_review", {})
        manual = reviewed(judgment)
        retrieval = ranking_metrics(dict.fromkeys(required, 1), ranked)
        total_claims = judgment.get("total_claims")
        unsupported_claims = judgment.get("unsupported_claims")
        unsupported_rate = (
            unsupported_claims / total_claims
            if manual
            and type(total_claims) is int
            and total_claims > 0
            and type(unsupported_claims) is int
            and 0 <= unsupported_claims <= total_claims
            else None
        )
        facts = gold.get("expected_facts", [])

        def canonical(fact):
            return json.dumps(
                {key: fact.get(key) for key in ("field", "value", "unit", "conditions")},
                sort_keys=True,
                ensure_ascii=False,
            )

        actual = {canonical(fact) for fact in prediction.get("facts", [])}
        observations.append(
            {
                "id": identifier,
                "category": gold["category"],
                "retrieval_recall_at_10": len(required & set(ranked)) / len(required)
                if required
                else None,
                "retrieval_recall_at_5": retrieval["recall_at_5"],
                "retrieval_mrr": retrieval["mrr"],
                "retrieval_ndcg_at_10": retrieval["ndcg_at_10"],
                "unsupported_conclusion_rate": unsupported_rate,
                "citation_validity": average(
                    [
                        (item["sha256"], item["page"]) in ranked and bool(verify_source(item))
                        for item in citations
                    ]
                ),
                "fact_correct": judgment.get("fact_correct")
                if manual and type(judgment.get("fact_correct")) is bool
                else None,
                "semantic_support": judgment.get("semantic_support")
                if manual and type(judgment.get("semantic_support")) is bool
                else None,
                "refusal_correct": (prediction.get("status") == "refused")
                == (not gold["answerable"]),
                "structured_fact_exactness": average([canonical(fact) in actual for fact in facts]),
                "source_count": len(citations),
                "human_reviewed": manual,
            }
        )
    keys = [
        "retrieval_recall_at_10",
        "retrieval_recall_at_5",
        "retrieval_mrr",
        "retrieval_ndcg_at_10",
        "unsupported_conclusion_rate",
        "citation_validity",
        "fact_correct",
        "semantic_support",
        "refusal_correct",
        "structured_fact_exactness",
    ]
    metrics = {
        key: {
            "value": average([row[key] for row in observations if row[key] is not None]),
            "cases": sum(row[key] is not None for row in observations),
        }
        for key in keys
    }
    return {
        "metrics": metrics,
        "observations": observations,
        "blocked": blocked,
        "coverage": sorted({row["category"] for row in observations}),
        "scored_cases": len(observations),
        "latency_ms": {
            key: latency_summary(
                [
                    value["latency_ms"][key]
                    for value in predictions.values()
                    if key in value.get("latency_ms", {})
                ]
            )
            for key in ("retrieval", "end_to_end")
        },
    }


class SourceVerifier:
    def __init__(self, manifest):
        self.entries = {item["sha256"]: item for item in manifest}
        self.texts = {}

    def __call__(self, item):
        try:
            sha, page, quote = item["sha256"], item["page"], item["quote"]
            if not isinstance(quote, str) or not quote.strip() or type(page) is not int or page < 1:
                return False
            key = (sha, page)
            if key not in self.texts:
                entry = self.entries[sha]
                if not entry.get("license"):
                    return False
                path = Path(entry["path"])
                path = path if path.is_absolute() else ROOT / path
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                    return False
                result = run_worker({"pdf_path": str(path), "page_numbers": [page]})
                self.texts[key] = next(
                    value["text"]
                    for value in result["pages"]
                    if value["page_number"] == page and not value.get("error_code")
                )

            def normalize(text):
                return re.sub(r"\s+", "", text)

            return normalize(quote) in normalize(self.texts[key])
        except (KeyError, OSError, ValueError, StopIteration, EngineError):
            return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from jsonschema import Draft202012Validator

    cases = read_jsonl(args.gold)
    validator = Draft202012Validator(
        json.loads((ROOT / "contracts/scientific-gold.schema.json").read_text())
    )
    for value in cases:
        validator.validate(value)
    predictions = read_jsonl(args.predictions)
    if len({item["id"] for item in cases}) != len(cases) or len(
        {item["id"] for item in predictions}
    ) != len(predictions):
        raise ValueError("DUPLICATE_CASE_ID")
    result = score(
        cases,
        {row["id"]: row for row in predictions},
        SourceVerifier(json.loads(args.manifest.read_text())),
    )
    approved = json.loads(args.thresholds.read_text())
    blockers = []
    if not cases or result["blocked"]:
        blockers.append("HUMAN_GOLD_OR_PREDICTION_INCOMPLETE")
    if set(result["coverage"]) != CATEGORIES:
        blockers.append("CATEGORY_COVERAGE_INCOMPLETE")
    if not result["observations"] or any(
        not row["human_reviewed"] for row in result["observations"]
    ):
        blockers.append("HUMAN_FACT_SUPPORT_REVIEW_MISSING")
    if any(value["cases"] == 0 for value in result["metrics"].values()):
        blockers.append("METRIC_COVERAGE_INCOMPLETE")
    if any(value["samples"] == 0 for value in result["latency_ms"].values()):
        blockers.append("LATENCY_MEASUREMENTS_MISSING")
    if len(result["observations"]) < approved.get("minimum_cases", 120):
        blockers.append("SAMPLE_SIZE_NOT_MET")
    if approved.get("approval_status") != "approved" or not approved.get("approved_by"):
        blockers.append("THRESHOLDS_NOT_APPROVED")
    result.update(
        status="BLOCKED" if blockers else "NOT_EXECUTED",
        gate_blockers=blockers,
        scope="offline human-gold evaluation; model self-review is ignored",
        threshold_status=approved.get("approval_status"),
    )
    if not blockers:
        thresholds = approved.get("minimum", {})
        if not thresholds:
            result["status"] = "BLOCKED"
            result["gate_blockers"].append("THRESHOLD_METRICS_MISSING")
        else:
            maximum = approved.get("maximum", {})
            result["status"] = (
                "PASS"
                if all(
                    result["metrics"].get(key, {}).get("value") is not None
                    and result["metrics"][key]["value"] >= value
                    for key, value in thresholds.items()
                )
                and all(
                    result["metrics"].get(key, {}).get("value") is not None
                    and result["metrics"][key]["value"] <= value
                    for key, value in maximum.items()
                )
                else "FAIL"
            )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "scientific-evaluation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "status",
                    "scored_cases",
                    "coverage",
                    "gate_blockers",
                    "threshold_status",
                )
            }
        )
    )
    return 0 if result["status"] == "PASS" else 2 if result["status"] == "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
