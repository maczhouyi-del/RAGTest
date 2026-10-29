"""Optional local relevance opinions. Scores are not calibrated across batches."""

from ragsystem.domain.errors import EngineError

REVIEW_POOL_LIMIT = 12
REVIEW_BATCH_SIZE = 6


def review_pool(baseline, candidates):
    """Retain every baseline context candidate, then spend spare slots on new content."""
    chosen = list(baseline[:8])
    seen_ids = {hit["chunk_id"] for hit in chosen}
    seen_content = {hit.get("content_sha256", hit["chunk_id"]) for hit in chosen}
    distinct, repeated = [], []
    for hit in candidates:
        if hit["chunk_id"] in seen_ids:
            continue
        seen_ids.add(hit["chunk_id"])
        digest = hit.get("content_sha256", hit["chunk_id"])
        (repeated if digest in seen_content else distinct).append(hit)
        seen_content.add(digest)
    return (chosen + distinct + repeated)[:REVIEW_POOL_LIMIT]


def review_order(generator, question, hits, *, max_candidates=6, before_call=None):
    if type(max_candidates) is not int or not 1 <= max_candidates <= REVIEW_POOL_LIMIT:
        raise EngineError("MODEL_RERANK_INVALID")
    selected = hits[:max_candidates]
    candidates = {f"R{index + 1}": hit for index, hit in enumerate(selected)}
    judgments, batches = {}, []
    keys = list(candidates)
    for start in range(0, len(keys), REVIEW_BATCH_SIZE):
        batch = keys[start : start + REVIEW_BATCH_SIZE]
        if before_call:
            before_call()
        response = generator.generate(
            "relevance",
            {
                "question": question,
                "candidates": [
                    {"candidate_id": key, "text": candidates[key]["preview"][:500]} for key in batch
                ],
            },
        )
        values = response.get("scores") if isinstance(response, dict) else None
        if not isinstance(values, list) or len(values) != len(batch):
            raise EngineError("MODEL_RERANK_INVALID")
        for value in values:
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("candidate_id"), str)
                or value["candidate_id"] not in batch
                or value["candidate_id"] in judgments
                or type(value.get("score")) is not int
                or not 0 <= value["score"] <= 5
                or not isinstance(value.get("reason"), str)
                or len(value["reason"]) > 160
            ):
                raise EngineError("MODEL_RERANK_INVALID")
            judgments[value["candidate_id"]] = value
        batches.append(batch)
    order = sorted(candidates, key=lambda key: -judgments[key]["score"])
    ranked = [candidates[key] for key in order] + hits[len(selected) :]
    return ranked, {
        "policy": "bounded-local-relevance-v2-batched"
        if max_candidates > 6
        else "bounded-local-relevance-v1",
        "fingerprint": generator.fingerprint,
        "baseline_chunk_ids": [hit["chunk_id"] for hit in hits],
        "ranked_chunk_ids": [hit["chunk_id"] for hit in ranked],
        "judgments": [
            {**judgments[key], "chunk_id": candidates[key]["chunk_id"]} for key in candidates
        ],
        "batches": batches,
        "score_interpretation": "uncalibrated local model opinion; batch-position bias not evaluated",
        "scientific_quality": "NOT_EVALUATED",
    }
