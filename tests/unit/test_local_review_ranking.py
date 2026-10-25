"""Protocol validation fixtures only, not real relevance model evaluations."""

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.retrieval.reranking import review_order


class Fixture:
    fingerprint = {"fixture": "engineering-only"}

    def __init__(self, scores):
        self.scores = scores

    def generate(self, task, data):
        assert task == "relevance" and all(len(row["text"]) <= 500 for row in data["candidates"])
        return {"scores": self.scores}


def test_relevance_stable_ties_preserve_source_text_and_capture_provenance():
    hits = [{"chunk_id": str(index), "preview": "原始引文" * 200} for index in range(3)]
    scores = [
        {"candidate_id": "R1", "score": 2, "reason": "fixture"},
        {"candidate_id": "R2", "score": 5, "reason": "fixture"},
        {"candidate_id": "R3", "score": 5, "reason": "fixture"},
    ]
    ranked, record = review_order(Fixture(scores), "question", hits)
    assert [row["chunk_id"] for row in ranked] == ["1", "2", "0"]
    assert all(row in hits for row in ranked) and ranked[0]["preview"] == hits[1]["preview"]
    assert (
        record["baseline_chunk_ids"] == ["0", "1", "2"]
        and record["fingerprint"] == Fixture.fingerprint
    )


@pytest.mark.parametrize(
    "scores",
    [
        [{"candidate_id": "R1", "score": 1, "reason": "fixture"}],
        [
            {"candidate_id": "R1", "score": 1, "reason": "fixture"},
            {"candidate_id": "R1", "score": 2, "reason": "duplicate"},
        ],
        [
            {"candidate_id": "R1", "score": True, "reason": "not integer"},
            {"candidate_id": "R2", "score": 5, "reason": "fixture"},
        ],
        [
            {"candidate_id": "R1", "score": 6, "reason": "range"},
            {"candidate_id": "R2", "score": 5, "reason": "fixture"},
        ],
        [
            {"candidate_id": "R1", "score": 2, "reason": "fixture"},
            {"candidate_id": "FORGED", "score": 5, "reason": "forged"},
        ],
    ],
)
def test_relevance_rejects_missing_duplicate_forged_or_invalid_scores(scores):
    with pytest.raises(EngineError, match="MODEL_RERANK_INVALID"):
        review_order(
            Fixture(scores),
            "question",
            [{"chunk_id": "a", "preview": "one"}, {"chunk_id": "b", "preview": "two"}],
        )
