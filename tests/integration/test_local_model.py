import os
from pathlib import Path

import pytest
from ragsystem.chunking.mapping import chunk_page
from ragsystem.domain.errors import EngineError
from ragsystem.indexing.embeddings import Embeddings
from ragsystem.models.local_onnx import LocalE5
from ragsystem.storage.database import Database


@pytest.mark.skipif(
    not os.environ.get("RAGSYSTEM_MODEL_DIR"),
    reason="Explicit local model path not supplied; no automatic download",
)
def test_real_approved_model_local_output_and_full_fingerprint(tmp_path):
    import numpy as np

    encoder = LocalE5(Path(os.environ["RAGSYSTEM_MODEL_DIR"]))
    vectors = encoder.encode(
        [
            "Dense passage retrieval uses a learned encoder.",
            "中文问题应如何检索英文论文？",
        ]
    )
    assert np.asarray(vectors).shape == (2, 384)
    assert np.isfinite(vectors).all()
    assert np.linalg.norm(vectors, axis=1) == pytest.approx([1, 1], abs=1e-5)
    assert encoder.encoded_texts == 2
    cache = Embeddings(Database(tmp_path / "research.db"))
    space = cache.space(encoder.fingerprint)
    cache.persist(space, "a" * 64, vectors[0])
    assert cache.get(space, "a" * 64) is not None

    with pytest.raises(EngineError, match="EMBEDDING_CONTEXT_LIMIT"):
        encoder.encode(["中" * 1200])
    chunks = list(chunk_page("中" * 1200))
    assert len(encoder.encode([chunk["text"] for chunk in chunks])) == len(chunks)
