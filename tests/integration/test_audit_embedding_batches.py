"""Synthetic vectors over public PDF chunks: persistence, not model quality."""
import math
from contextlib import contextmanager
from pathlib import Path

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.indexing.incremental import embed_visible
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.parsing.pipeline import Parser
from ragsystem.storage.database import Database


class Encoder:
    fingerprint = {
        'model': 'SYNTHETIC_NOT_A_MODEL', 'revision': '1', 'weight_sha256': 'a'*64,
        'tokenizer_sha256': 'b'*64, 'preprocessing': {}, 'dimension': 3,
        'metric': 'cosine', 'normalization': 'none',
    }

    def __init__(self, invalid=False):
        self.texts = 0
        self.invalid = invalid

    def encode(self, texts):
        self.texts += len(texts)
        vectors = [[1, 0, 0] for _ in texts]
        if self.invalid:
            vectors[1] = [float('nan'), 0, 0]
        return vectors


def store(tmp_path):
    db = Database(tmp_path/'data/research.db')
    fixture = Path(__file__).resolve().parents[1]/'fixtures/public/N19-1423.pdf'
    version = PdfImporter(db, tmp_path).import_path_for_test(fixture, 'import')['doc_version_id']
    Parser(db, tmp_path).parse(version, 'parse')
    return db


def test_bounded_transactions_cache_reuse_and_links(tmp_path):
    db = store(tmp_path)
    transactions = []
    original = db.transaction

    @contextmanager
    def counted():
        transactions.append(1)
        with original() as conn:
            yield conn
    db.transaction = counted
    encoder = Encoder()
    result = embed_visible(db, encoder)
    assert encoder.texts == result['new_embeddings'] > 8
    assert len(transactions) <= 2 + math.ceil(result['new_embeddings']/8) + math.ceil(result['chunks']/128)
    with db.connection() as conn:
        assert conn.execute('SELECT count(*) FROM chunk_embedding_links').fetchone()[0] == result['chunks']
    transactions.clear()
    again = embed_visible(db, encoder)
    assert again['new_embeddings'] == 0 and encoder.texts == result['new_embeddings']
    assert len(transactions) <= 2 + math.ceil(result['chunks']/128)
    assert db.integrity()['foreign_key_check'] == []


def test_invalid_batch_rolls_back_and_retry_reuses_only_committed_records(tmp_path):
    db = store(tmp_path)
    with pytest.raises(EngineError, match='VECTOR_INVALID'):
        embed_visible(db, Encoder(invalid=True))
    with db.connection() as conn:
        assert conn.execute('SELECT count(*) FROM embedding_records').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM chunk_embedding_links').fetchone()[0] == 0
    result = embed_visible(db, Encoder())
    assert result['new_embeddings'] > 8


def test_cancel_after_inference_preserves_cache_and_never_publishes(tmp_path):
    db = store(tmp_path)
    encoder = Encoder()
    def check(current, total):
        if encoder.texts:
            raise EngineError("LEASE_LOST")
    with pytest.raises(EngineError, match="LEASE_LOST"):
        embed_visible(db, encoder, progress=check)
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) FROM embedding_records").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM index_generations").fetchone()[0] == 0
    result = embed_visible(db, Encoder())
    assert result["new_embeddings"] > 8
