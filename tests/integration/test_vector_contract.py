import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.vector_adapters.lancedb import LanceDB
from ragsystem.vector_adapters.sqlite_vec import SQLiteVec


@pytest.fixture(params=[SQLiteVec, LanceDB])
def adapter(request, tmp_path):
    return request.param(tmp_path / request.param.__name__, "synthetic_space", 3)


def test_exact_scope_incremental_delete_restart_and_integrity(adapter):
    # Explicit numeric engineering fixture, not a model/corpus benchmark.
    entries = [
        ("out_of_scope", [1, 0, 0]),
        ("allowed", [0.9, 0.1, 0]),
        ("far", [0, 1, 0]),
    ]
    adapter.upsert(entries)
    assert adapter.search_exact([1, 0, 0], {"allowed", "far"}, 1)[0]["embedding_id"] == "allowed"
    assert adapter.search_exact([1, 0, 0], set(), 2) == []
    adapter.upsert([("allowed", [0, 0, 1])])
    assert len(adapter.ids()) == 3
    adapter.delete(["far"])
    assert adapter.check_integrity(["allowed", "out_of_scope"])["ok"]
    reopened = type(adapter)(adapter.path, "synthetic_space", 3)
    assert reopened.ids() == {"allowed", "out_of_scope"}
    with pytest.raises(EngineError, match="INDEX_INCOMPLETE"):
        adapter.search_exact([1, 0, 0], {"far"}, 1)


def test_ties_and_invalid_inputs(adapter):
    adapter.upsert([("a", [1, 0, 0]), ("b", [1, 0, 0])])
    assert adapter.search_exact([1, 0, 0], {"b", "a"}, 1)[0]["embedding_id"] == "a"
    for query in [[1, 0], [float("nan"), 0, 0], [0, 0, 0]]:
        with pytest.raises(EngineError, match="VECTOR_INVALID"):
            adapter.search_exact(query, {"a"}, 1)
    with pytest.raises(EngineError, match="K_INVALID"):
        adapter.search_exact([1, 0, 0], {"a"}, 0)
    with pytest.raises(EngineError, match="VECTOR_ID_INVALID"):
        adapter.delete(["x'); DROP TABLE vectors;--"])
    assert adapter.rebuild([("c", [1, 1, 0])])["ok"]


@pytest.mark.parametrize("backend", [SQLiteVec, LanceDB])
def test_l2_matches_independent_distance_and_invalid_rebuild_preserves_index(tmp_path, backend):
    adapter = backend(tmp_path / backend.__name__, "l2_fixture", 3, "l2")
    adapter.upsert([("distance_five", [4, 4, 0])])
    result = adapter.search_exact([1, 0, 0], {"distance_five"}, 1)
    assert result[0]["distance"] == pytest.approx(5.0, abs=1e-6)
    with pytest.raises(EngineError, match="VECTOR_INVALID"):
        adapter.rebuild([("bad", [1, 2])])
    assert adapter.ids() == {"distance_five"}
    with pytest.raises(EngineError, match="SPACE_MISMATCH"):
        backend(adapter.path, "l2_fixture", 4, "l2")
