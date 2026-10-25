"""MVP safety and retrieval engineering cases, separate from scientific gold."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ragsystem.chunking.mapping import chunk_page
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.retrieval.source_search import Sources
from ragsystem.retrieval.tokenizer import index_terms, tokenize
from ragsystem.storage.database import Database
from ragsystem.workflows.workbench import Workbench

ROOT = Path(__file__).resolve().parents[2]


def store(tmp_path):
    root = tmp_path / "mvp"
    db = Database(root / "data/research.db")
    version = PdfImporter(db, root).import_path_for_test(
        ROOT / "tests/fixtures/public/N19-1423.pdf", "bert"
    )["doc_version_id"]
    return root, db, version


def test_overlapping_chunks_cover_boundaries_and_keep_exact_offsets():
    text = "甲" * 385 + "跨边界证据模型数据" + "乙" * 700 + "。\nEnd of paper."
    chunks = list(chunk_page(text))
    assert len(chunks) > 2 and all(len(c["text"]) <= 400 for c in chunks)
    assert any("跨边界证据模型数据" in c["text"] for c in chunks)
    assert chunks[0]["start"] == 0 and chunks[-1]["end"] == len(text)
    for a, b in zip(chunks, chunks[1:]):
        assert a["start"] < b["start"] < a["end"]
    for c in chunks:
        assert text[c["start"] : c["end"]] == c["text"]


def test_keyword_index_preserves_tf_single_han_and_fullwidth_normalization(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "base")
    assert tokenize("模型 模型 ＢＥＲＴ", unigrams=True).count("模型") == 2
    with db.transaction() as conn:
        rows = conn.execute("SELECT id FROM chunks ORDER BY id LIMIT 2").fetchall()
        for row, text in zip(rows, ["模型 模型 模型 模型 分析", "模型 分析 数据 论文 实验"]):
            conn.execute("UPDATE chunks SET clean_text=? WHERE id=?", (text, row[0]))
            # Explicit synthetic retrieval fixture; not a PDF alignment gold case.
            conn.execute("DELETE FROM chunks_terms_v2 WHERE chunk_id=?", (row[0],))
            conn.execute("DELETE FROM terms_indexed_chunks_v2 WHERE chunk_id=?", (row[0],))
            index_terms(conn, row[0], text)
    sources = Sources(db, root)
    assert sources.search("模型", [version], 5, terms=True)[0]["chunk_id"] == rows[0][0]
    assert sources.search("模", [version], 5, terms=True)
    assert sources.search("ＢＥＲＴ", [version], 5, terms=True)


def test_prepare_endpoint_real_pdf_is_idempotent_and_retains_source(tmp_path):
    root, db, version = store(tmp_path)
    token = "a" * 64
    with TestClient(
        create_app(token, root), base_url="http://127.0.0.1", headers={"X-RAG-Session": token}
    ) as client:
        body = {"version_ids": [version], "idempotency_key": "prepare"}
        response = client.post("/v0/mvp/prepare", json=body)
        assert response.status_code == 202
        job = Jobs(db).get(response.json()["job_id"])
        assert job["status"] == "completed" and job["result_ref"].endswith("needs_embedding_model")
        assert client.post("/v0/mvp/prepare", json=body).json()["job_id"] == job["id"]
        assert (
            client.post(
                "/v0/mvp/prepare", json={**body, "version_ids": [version, version]}
            ).status_code
            == 400
        )
    assert (
        Sources(db, root).anchor(Sources(db, root).search("BERT", [version], 1)[0]["chunk_id"])[
            "bbox_norm"
        ]
        is None
    )


def test_no_sources_refuses_without_loading_any_generator(tmp_path, monkeypatch):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "base")
    work = Workbench(db, root, HybridSearch(db, root))

    def forbidden():
        raise AssertionError("no-evidence model call")

    monkeypatch.setattr(work.generation, "require", forbidden)
    row = work.create_answer("xyzzy_missing_928461", [version], None, "generative", "keyword")
    work.run_answer(row["id"])
    result = work.answers(None, run_id=row["id"])[0]
    assert result["status"] == "refused" and result["claims"] == [] and result["evidence"] == []


@pytest.mark.skipif(
    not os.environ.get("RAGSYSTEM_MODEL_DIR"), reason="explicit approved E5 required"
)
def test_real_e5_restart_corruption_and_generation_switch_do_not_reembed(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "base")
    search = HybridSearch(db, root)
    jobs = Jobs(db)
    directory = Directories().issue(Path(os.environ["RAGSYSTEM_MODEL_DIR"]), "embedding")

    def build(key):
        row = jobs.enqueue("embed_batch", key, {})
        search.build(row["id"], directory, "sqlite-vec")
        assert jobs.get(row["id"])["status"] == "completed"

    build("first")
    initial = search.config()
    restarted = HybridSearch(Database(db.path), root)
    assert restarted.status()["ready"]
    assert restarted.search("BERT pre-training tasks", [version], 5, None, "hybrid")["results"]
    with db.connection() as conn:
        before = conn.execute("SELECT COUNT(*) FROM embedding_records").fetchone()[0]
    from ragsystem.models.provider_registry import ProviderRegistry

    registry = ProviderRegistry(db)
    connection = registry.save(
        {
            "id": None,
            "name": "offline configuration",
            "kind": "api",
            "base_url": "http://127.0.0.1:1/v1",
            "model": "model-one",
            "expected_revision": 0,
        },
        "",
    )
    registry.save(
        {**connection, "expected_revision": connection["revision"], "model": "model-two"}, ""
    )
    assert restarted.status()["ready"]
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM embedding_records").fetchone()[0] == before
    path = root / initial["relative_path"]
    data = path.read_bytes()
    path.write_bytes(b"broken" + data[6:])
    assert not restarted.status()["ready"] and restarted.status()["reason"] == "INDEX_INVALID"
    with pytest.raises(EngineError, match="INDEX_REBUILD_REQUIRED"):
        restarted.search("BERT", [version], 5, None, "hybrid")
    build("repair")
    assert search.config()["new_embeddings"] == 0
    assert search.status()["ready"] and path.read_bytes().startswith(b"broken")
    assert hashlib.sha256(
        (
            root
            / "papers"
            / (
                json.loads(jobs.get(jobs.find_key("import", "bert")["id"])["payload_json"])[
                    "sha256"
                ]
                + ".pdf"
            )
        ).read_bytes()
    ).hexdigest()


def test_parent_cancel_prevents_late_parse_publication_and_retains_previous_chunks(
    tmp_path, monkeypatch
):
    import ragsystem.parsing.pipeline as pipeline

    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "old")
    with db.connection() as conn:
        before = [
            tuple(row)
            for row in conn.execute("SELECT id,clean_text FROM chunks WHERE visible=1 ORDER BY id")
        ]
    jobs = Jobs(db)
    parent = jobs.enqueue("verify", "parent", {})
    lease = jobs.claim(parent["id"], lease_seconds=1800)
    original = pipeline.run_worker

    def cancelled_after_worker(*args, **kwargs):
        result = original(*args, **kwargs)
        jobs.cancel(parent["id"])
        return result

    def check(connection=None):
        if connection is not None:
            jobs.require_lease(connection, parent["id"], lease["lease_token"])
        else:
            with db.connection() as conn:
                jobs.require_lease(conn, parent["id"], lease["lease_token"])

    monkeypatch.setattr(pipeline, "run_worker", cancelled_after_worker)
    with pytest.raises(EngineError):
        Parser(db, root).parse(version, "new", parent_check=check)
    with db.connection() as conn:
        assert [
            tuple(row)
            for row in conn.execute("SELECT id,clean_text FROM chunks WHERE visible=1 ORDER BY id")
        ] == before
    assert jobs.get(parent["id"])["status"] == "cancelled"


def test_mvp_answer_preserves_top_eight_without_legacy_three_per_paper_cutoff(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    expected = work.search.search("BERT", [version], 8, None, "keyword", 8)["results"]
    run = work.create_answer("BERT", [version], None, "extractive", "keyword", per_paper_limit=8)
    work.run_answer(run["id"])
    answer = work.answers(None, run_id=run["id"])[0]
    assert answer["status"] == "completed"
    assert len(answer["evidence"]) == len(expected) == 8
    assert {e["source_anchor_id"] for e in answer["evidence"]} == {
        item["chunk_id"] for item in expected
    }
