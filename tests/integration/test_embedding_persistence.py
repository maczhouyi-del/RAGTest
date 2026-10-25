import hashlib

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.indexing.embeddings import Embeddings
from ragsystem.storage.database import Database


def fingerprint():
    return {
        "model": "SYNTHETIC_ENGINEERING_FIXTURE_NOT_A_MODEL",
        "revision": "test-v1",
        "weight_sha256": "a" * 64,
        "tokenizer_sha256": "b" * 64,
        "preprocessing": {"prefix": "test"},
        "dimension": 3,
        "metric": "cosine",
        "normalization": "none",
    }


def test_persistence_reuse_and_changed_fingerprints(tmp_path):
    path = tmp_path / "research.db"
    cache = Embeddings(Database(path))
    space = cache.space(fingerprint())
    content = hashlib.sha256(b"engineering content").hexdigest()
    record = cache.persist(space, content, [1, 0, 0])
    assert cache.persist(space, content, [1, 0, 0]) == record
    reopened = Embeddings(Database(path))
    assert reopened.get(space, content)["id"] == record
    different = cache.space({**fingerprint(), "tokenizer_sha256": "c" * 64})
    assert different != space and reopened.get(different, content) is None
    with pytest.raises(EngineError, match="EMBEDDING_CONFLICT"):
        cache.persist(space, content, [0, 1, 0])


@pytest.mark.parametrize(
    "vector",
    [[1, 0], [float("nan"), 0, 0], [float("inf"), 0, 0], [1e100, 0, 0], [0, 0, 0]],
)
def test_invalid_vectors_never_persist(tmp_path, vector):
    cache = Embeddings(Database(tmp_path / "research.db"))
    space = cache.space(fingerprint())
    with pytest.raises(EngineError, match="VECTOR_INVALID"):
        cache.persist(space, "a" * 64, vector)
    assert cache.get(space, "a" * 64) is None
