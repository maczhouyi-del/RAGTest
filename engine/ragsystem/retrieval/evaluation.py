"""Offline metric arithmetic; labels must come from independent human review."""

import math
import statistics


def ranking_metrics(relevance, ranked):
    if any(type(grade) is not int or not 0 <= grade <= 3 for grade in relevance.values()):
        raise ValueError("INVALID_RELEVANCE_GRADE")
    required = {key for key, grade in relevance.items() if grade > 0}
    # Repeated result IDs still consume a rank, but never receive credit twice.
    seen, grades = set(), []
    for key in ranked:
        grades.append(relevance.get(key, 0) if key not in seen else 0)
        seen.add(key)
    ideal = sorted(relevance.values(), reverse=True)[:10]

    def dcg(values):
        return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(values))

    return {
        "recall_at_5": len(required & set(ranked[:5])) / len(required) if required else None,
        "recall_at_10": len(required & set(ranked[:10])) / len(required) if required else None,
        "mrr": next((1 / index for index, grade in enumerate(grades, 1) if grade > 0), 0)
        if required
        else None,
        "ndcg_at_10": dcg(grades[:10]) / dcg(ideal) if required else None,
    }


def latency_summary(values):
    if not values:
        return {"samples": 0, "p50": None, "p95": None}
    if any(
        type(value) not in {int, float} or not math.isfinite(value) or value < 0 for value in values
    ):
        raise ValueError("INVALID_LATENCY")
    ordered = sorted(values)
    return {
        "samples": len(values),
        "p50": statistics.median(ordered),
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
    }
