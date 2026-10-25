"""Optional bounded relevance opinions, using the explicitly configured local candidate."""

from ragsystem.domain.errors import EngineError


def review_order(generator, question, hits):
    selected = hits[:6]
    candidates = {f"R{index + 1}": hit for index, hit in enumerate(selected)}
    response = generator.generate(
        "relevance",
        {
            "question": question,
            "candidates": [
                {"candidate_id": key, "text": hit["preview"][:500]}
                for key, hit in candidates.items()
            ],
        },
    )
    if not isinstance(response, dict):
        raise EngineError("MODEL_RERANK_INVALID")
    values = response.get("scores")
    if not isinstance(values, list) or len(values) != len(candidates):
        raise EngineError("MODEL_RERANK_INVALID")
    judgments = {}
    for value in values:
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("candidate_id"), str)
            or value.get("candidate_id") not in candidates
            or value["candidate_id"] in judgments
            or type(value.get("score")) is not int
            or not 0 <= value["score"] <= 5
            or not isinstance(value.get("reason"), str)
            or len(value["reason"]) > 160
        ):
            raise EngineError("MODEL_RERANK_INVALID")
        judgments[value["candidate_id"]] = value
    order = sorted(candidates, key=lambda key: -judgments[key]["score"])
    ranked = [candidates[key] for key in order] + hits[len(selected) :]
    return ranked, {
        "policy": "bounded-local-relevance-v1",
        "fingerprint": generator.fingerprint,
        "baseline_chunk_ids": [hit["chunk_id"] for hit in hits],
        "ranked_chunk_ids": [hit["chunk_id"] for hit in ranked],
        "judgments": [
            {**judgments[key], "chunk_id": candidates[key]["chunk_id"]} for key in candidates
        ],
        "scientific_quality": "NOT_EVALUATED",
    }
