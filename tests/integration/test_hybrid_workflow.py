import os
from pathlib import Path

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.retrieval.tokenizer import search_terms
from ragsystem.storage.database import Database

ROOT = Path(__file__).resolve().parents[2]


def test_versioned_cjk_tokenization_keeps_mixed_words_separate():
    assert search_terms("BERT材料科学模型") == ["bert", "材料", "料科", "科学", "学模", "模型"]
    assert search_terms('retrieval; "DROP TABLE"') == ["retrieval", "drop", "table"]


@pytest.mark.skipif(
    not os.environ.get("RAGSYSTEM_MODEL_DIR"), reason="No explicit approved local model directory"
)
def test_real_model_index_backend_switch_cache_scope_restart_and_failed_publish(
    tmp_path, monkeypatch
):
    root = tmp_path / "工作区"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "one"
    )["doc_version_id"]
    Parser(db, root).parse(version, "parse")
    search, jobs = HybridSearch(db, root), Jobs(db)
    directory = Directories().issue(Path(os.environ["RAGSYSTEM_MODEL_DIR"]), "embedding")

    def build(backend, key):
        row = jobs.enqueue("embed_batch", key, {"test_only": key})
        search.build(row["id"], directory, backend)
        return jobs.get(row["id"])

    assert build("sqlite-vec", "first")["status"] == "completed"
    initial = search.config()
    assert initial["new_embeddings"] > 0 and search.status()["ready"]
    assert build("lancedb", "candidate-switch")["status"] == "completed"
    assert search.config()["new_embeddings"] == 0
    reopened = HybridSearch(Database(db.path), root)
    result = reopened.search("How does BERT pretraining work?", [version], 5, None, "hybrid")
    assert result["results"] and all(hit["doc_version_id"] == version for hit in result["results"])
    for hit in result["results"]:
        assert reopened.sources.anchor(hit["source_anchor_id"])["file_sha256"]
    previous = search.config()

    def fail(*args):
        raise EngineError("INJECTED_INDEX_FAILURE")

    monkeypatch.setattr(search, "adapter", fail)
    assert build("sqlite-vec", "failed-publish")["status"] == "failed"
    assert search.config() == previous
    Parser(db, root).parse(version, "reparse")
    assert not reopened.status()["ready"]
    with pytest.raises(EngineError, match="INDEX_REBUILD_REQUIRED"):
        reopened.search("BERT", [version], 5, None, "vector_exact")


@pytest.mark.skipif(
    not os.environ.get("RAGSYSTEM_MODEL_DIR"), reason="explicit approved E5 directory required"
)
def test_metadata_and_visibility_are_rechecked_after_real_query_encoding(tmp_path, monkeypatch):
    from ragsystem.library.lifecycle import Lifecycle
    from ragsystem.library.repository import Library

    root = tmp_path / "范围"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "one"
    )["doc_version_id"]
    Parser(db, root).parse(version, "parse")
    document = Library(db).list_documents()[0]

    def metadata(revision, tags):
        return Library(db).update_metadata(
            document["document_id"],
            {
                "expected_revision": revision,
                "title": "BERT",
                "authors": [],
                "year": 2019,
                "doi": None,
                "venue": "",
                "tags": tags,
            },
        )

    metadata(0, ["selected"])
    search = HybridSearch(db, root)
    jobs = Jobs(db)
    row = jobs.enqueue("embed_batch", "index", {})
    search.build(
        row["id"],
        Directories().issue(Path(os.environ["RAGSYSTEM_MODEL_DIR"]), "embedding"),
        "sqlite-vec",
    )
    assert jobs.get(row["id"])["status"] == "completed"
    with pytest.raises(EngineError, match="SCOPE_FILTER_CHANGED"):
        search.search("BERT", [version], 5, None, "keyword", filters={"year_from": 2020})
    assert search.search(
        "BERT",
        [version],
        5,
        None,
        "keyword",
        filters={"tag": "selected", "year_from": 2018, "year_to": 2020},
    )["results"]
    encode = search.encoder.encode

    def metadata_changed(*args, **kwargs):
        metadata(1, ["changed"])
        return encode(*args, **kwargs)

    monkeypatch.setattr(search.encoder, "encode", metadata_changed)
    with pytest.raises(EngineError, match="SCOPE_FILTER_CHANGED"):
        search.search("BERT", [version], 5, None, "hybrid", filters={"tag": "selected"})

    def withdrawn(*args, **kwargs):
        Lifecycle(db).update(document["document_id"], 0, "retracted", "test concurrent manual flag")
        return encode(*args, **kwargs)

    monkeypatch.setattr(search.encoder, "encode", withdrawn)
    with pytest.raises(EngineError, match="SCOPE_NOT_AVAILABLE"):
        search.search("BERT", [version], 5, None, "hybrid")
