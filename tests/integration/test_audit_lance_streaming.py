import pytest
from ragsystem.vector_adapters.lancedb import LanceDB


@pytest.mark.parametrize('metric', ['cosine', 'l2'])
def test_streamed_exact_scope_and_ties_without_vectors(tmp_path, monkeypatch, metric):
    from lancedb.query import LanceVectorQueryBuilder

    adapter = LanceDB(tmp_path/'lance', 'engineering_fixture', 3, metric)
    entries = [(f'id_{n:05}', [1, 0, 0] if n % 2 else [0, 1, 0]) for n in range(3000)]
    adapter.upsert(entries)
    eligible = {key for key, _ in entries if int(key[3:]) % 3}
    expected = sorted(key for key, vector in entries if key in eligible and vector == [1, 0, 0])[:7]
    batch_sizes = []
    original = LanceVectorQueryBuilder.to_batches

    def batches(self, batch_size=None, **kwargs):
        for batch in original(self, batch_size, **kwargs):
            assert 'vector' not in batch.schema.names
            batch_sizes.append(batch.num_rows)
            yield batch

    def forbidden(*args, **kwargs):
        raise AssertionError('whole-table/vector materialization')

    monkeypatch.setattr(LanceVectorQueryBuilder, 'to_batches', batches)
    monkeypatch.setattr(adapter.table, 'to_arrow', forbidden)
    result = adapter.search_exact([1, 0, 0], eligible, 7)
    assert [row['embedding_id'] for row in result] == expected
    assert len(batch_sizes) > 1 and max(batch_sizes) <= 256
    assert adapter.ids() == {key for key, _ in entries}
    assert adapter.search_exact([1, 0, 0], {expected[0]}, 7)[0]['embedding_id'] == expected[0]
    assert adapter.search_exact([1, 0, 0], set(), 7) == []
