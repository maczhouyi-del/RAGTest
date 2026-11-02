"""Real parser fixtures; filter semantics tests are not scientific quality scores."""

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from test_mvp_core import store


@pytest.mark.parametrize(
    "filters", [{"year_from": 2020}, {"tag": "missing"}, {"year_to": 2020}]
)
def test_missing_metadata_returns_empty_before_any_retriever(
    tmp_path, monkeypatch, filters
):
    root, db, version = store(tmp_path)
    search = HybridSearch(db, root)
    monkeypatch.setattr(
        search.sources, "search", lambda *a, **kw: pytest.fail("empty scope retrieved")
    )
    assert (
        search.search("BERT", [version], 5, None, "hybrid", filters=filters)[
            "scope_status"
        ]
        == "NO_FILTER_MATCH"
    )


def test_filter_intersection_authorization_and_concurrent_revision(
    tmp_path, monkeypatch
):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    library = Library(db)
    document = library.list_documents()[0]
    library.update_metadata(
        document["document_id"],
        {
            "expected_revision": 0,
            "title": "fixture",
            "year": 2019,
            "tags": ["selected"],
        },
    )
    search = HybridSearch(db, root)
    filters = {"year_from": 2018, "year_to": 2020, "tag": "selected"}
    assert search.search("BERT", [version], 5, None, "keyword", filters=filters)[
        "results"
    ]
    project = library.create_project("unauthorized")
    with pytest.raises(EngineError, match="SCOPE_NOT_AVAILABLE"):
        search.search("BERT", [version], 5, project["id"], "keyword", filters=filters)
    original = search.sources.search

    def change(*args, **kwargs):
        hits = original(*args, **kwargs)
        library.update_metadata(
            document["document_id"],
            {
                "expected_revision": 1,
                "title": "changed",
                "year": 2019,
                "tags": ["selected"],
            },
        )
        return hits

    monkeypatch.setattr(search.sources, "search", change)
    with pytest.raises(EngineError, match="SCOPE_FILTER_CHANGED"):
        search.search("BERT", [version], 5, None, "keyword", filters=filters)
