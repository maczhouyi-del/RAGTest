"""Synthetic ranking oracles on real SQLite; these are not scientific relevance gold."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.retrieval.source_search import Sources
from test_embedding_persistence import fingerprint
from test_mvp_core import store


def ranked_store(tmp_path, monkeypatch):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    search = HybridSearch(db, root)
    with db.transaction() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM chunks ORDER BY id LIMIT 4")]
        # First vector has two different source chunks. Text edits here are explicit
        # synthetic retrieval fixtures, never used for source alignment assertions.
        for row, text in zip(rows, ["duplicate content", "duplicate content", "second", "third"]):
            row["content_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            conn.execute(
                "UPDATE chunks SET clean_text=?,content_sha256=? WHERE id=?",
                (text, row["content_sha256"], row["id"]),
            )
    space = search.cache.space(fingerprint())
    ids = []
    for row in rows:
        existing = search.cache.get(space, row["content_sha256"])
        embedding = (
            existing["id"]
            if existing
            else search.cache.persist(space, row["content_sha256"], [1, 0, 0])
        )
        search.cache.link(row["id"], embedding)
        if embedding not in ids:
            ids.append(embedding)
    with db.transaction() as conn:
        config = {
            "space_id": space,
            "backend": "sqlite-vec",
            "relative_path": "test-only.db",
            "model_dir": "SYNTHETIC",
            "fingerprint": fingerprint(),
            "generation": "fixture",
            "chunk_fingerprint": search.fingerprint(conn),
        }
        conn.execute(
            "INSERT INTO app_settings VALUES('active_index',?,'test')", (json.dumps(config),)
        )
    search.encoder_path = "SYNTHETIC"
    search.encoder = SimpleNamespace(
        fingerprint=fingerprint(), dimension=3, encode=lambda *args, **kw: [[1, 0, 0]]
    )
    monkeypatch.setattr(search, "status", lambda: {"ready": True})
    adapter_calls = []

    def exact(query, eligible, k):
        adapter_calls.append((eligible, k))
        return [
            {"embedding_id": identifier, "distance": index / 10}
            for index, identifier in enumerate(ids)
        ]

    monkeypatch.setattr(search, "adapter", lambda *args: SimpleNamespace(search_exact=exact))
    lexical = [
        {
            "chunk_id": rows[2]["id"],
            "doc_version_id": version,
            "rank": 1,
            "source_anchor_id": rows[2]["id"],
            "page_number": rows[2]["page_number"],
            "preview": "second",
            "content_sha256": rows[2]["content_sha256"],
        }
    ]
    monkeypatch.setattr(search.sources, "search", lambda *args, **kw: lexical)
    return search, version, rows, adapter_calls


def test_rrf_preserves_embedding_rank_after_one_to_many_expansion(tmp_path, monkeypatch):
    search, version, rows, calls = ranked_store(tmp_path, monkeypatch)
    response = search.search("query", [version], 8, None, "hybrid")
    results = {row["chunk_id"]: row for row in response["results"]}
    assert results[rows[2]["id"]]["vector_rank"] == 2
    assert results[rows[2]["id"]]["lexical_rank"] == 1
    assert results[rows[2]["id"]]["rrf_score"] == pytest.approx(1 / 61 + 1 / 62)
    assert results[rows[0]["id"]]["vector_rank"] == 1
    assert results[rows[1]["id"]]["vector_rank"] == 1
    assert results[rows[0]["id"]]["rrf_score"] == pytest.approx(1 / 61)
    assert results[rows[1]["id"]]["rrf_score"] == pytest.approx(1 / 61)
    assert calls[0][1] == 50
    assert len(results) == 4
    assert all(
        row["source_anchor_id"] == key and row["doc_version_id"] == version
        for key, row in results.items()
    )
    assert search.search("query", [version], 8, None, "hybrid")["results"] == response["results"]


def test_vector_ranks_and_duplicate_content_do_not_consume_all_context(tmp_path, monkeypatch):
    search, version, rows, _calls = ranked_store(tmp_path, monkeypatch)
    response = search.search("query", [version], 3, None, "vector_exact")
    hits = response["results"]
    assert [hit["vector_rank"] for hit in hits] == [1, 2, 3]
    assert len({hit["content_sha256"] for hit in hits}) == 3
    assert {item["chunk_id"] for item in hits[0]["content_sources"]} == {
        rows[0]["id"],
        rows[1]["id"],
    }
    expanded = search.search("query", [version], 8, None, "vector_exact")["results"]
    assert {hit["chunk_id"] for hit in expanded} == {row["id"] for row in rows}
    assert [hit["rank"] for hit in expanded] == [1, 2, 3, 4]


@pytest.mark.parametrize(
    "strategy,k", [("unknown", 8), ("keyword", 0), ("keyword", 101), ("keyword", True)]
)
def test_direct_hybrid_parameter_boundaries(tmp_path, strategy, k):
    root, db, version = store(tmp_path)
    with pytest.raises(EngineError, match="INVALID_SEARCH"):
        HybridSearch(db, root).search("BERT", [version], k, None, strategy)


@pytest.mark.parametrize(
    "text", ["中文连续文本材料科学", "BERT alpha-2 10 mg/mL", '" OR * - : NEAR(x)']
)
def test_literal_and_keyword_tokens_are_safe_and_preserve_original(tmp_path, text):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    # Separate synthetic FTS fixture; the original PDF and source-mapping tables stay intact.
    with db.transaction() as conn:
        chunk = conn.execute("SELECT id FROM chunks ORDER BY id LIMIT 1").fetchone()[0]
        conn.execute("UPDATE chunks SET clean_text=? WHERE id=?", (text, chunk))
        conn.execute("UPDATE chunks_fts SET clean_text=? WHERE chunk_id=?", (text, chunk))
        conn.execute("DELETE FROM chunks_terms_v2 WHERE chunk_id=?", (chunk,))
        conn.execute("DELETE FROM terms_indexed_chunks_v2 WHERE chunk_id=?", (chunk,))
    source = Sources(db, root)
    assert source.search(text, [version], 50)[0]["preview"] == text
    assert source.search(text, [version], 50, terms=True)[0]["preview"] == text
    assert source.search("zzzz94783562", [version], 50, terms=True) == []


def test_cross_paper_duplicate_content_keeps_all_source_associations(tmp_path):
    from ragsystem.ingestion.import_pdf import PdfImporter
    from test_mvp_core import ROOT

    root, db, one = store(tmp_path)
    two = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/2020.emnlp-main.550.pdf", "other"
    )["doc_version_id"]
    # Ranking-only fixture: no invented text is published as a real PDF quote.
    hits = [
        {
            "chunk_id": "a",
            "source_anchor_id": "a",
            "doc_version_id": one,
            "page_number": 1,
            "content_sha256": "same",
        },
        {
            "chunk_id": "b",
            "source_anchor_id": "b",
            "doc_version_id": one,
            "page_number": 2,
            "content_sha256": "same",
        },
        {
            "chunk_id": "c",
            "source_anchor_id": "c",
            "doc_version_id": two,
            "page_number": 3,
            "content_sha256": "same",
        },
        {
            "chunk_id": "d",
            "source_anchor_id": "d",
            "doc_version_id": two,
            "page_number": 4,
            "content_sha256": "different",
        },
    ]
    search = HybridSearch(db, root)
    result = search.paper_quota(hits, 2, 3)
    assert [hit["chunk_id"] for hit in result] == ["a", "d"]
    assert result[0]["content_sources"] == [
        {key: hit[key] for key in ("chunk_id", "doc_version_id", "source_anchor_id", "page_number")}
        for hit in hits[:3]
    ]
    assert [hit["chunk_id"] for hit in search.paper_quota(hits, 8, 3)] == ["a", "d", "b", "c"]


def test_rrf_equal_scores_are_deterministic_and_duplicate_links_do_not_add_votes():
    a = {"chunk_id": "a", "vector_rank": 1}
    b = {"chunk_id": "b", "vector_rank": 1}
    result = HybridSearch.fuse([], [b, a, a])
    assert [hit["chunk_id"] for hit in result] == ["a", "b"]
    assert all(hit["rrf_score"] == pytest.approx(1 / 61) for hit in result)
