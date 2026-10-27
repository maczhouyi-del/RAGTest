"""Deterministic runtime metadata is never PDF evidence or an inference request."""

import json

import pytest
from fastapi.testclient import TestClient
from ragsystem.ipc.server import create_app
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.workflows.system_information import system_information_topic
from ragsystem.workflows.workbench import Workbench
from test_generation_providers import protocol_server, values
from test_mvp_core import store


@pytest.mark.parametrize(
    "question,topic",
    [
        ("你是什么模型？", "generation"),
        ("当前生成模型是什么？", "generation"),
        ("现在使用什么 Embedding 模型？", "embedding"),
        ("WHAT model are you?", "generation"),
        ("BERT 使用了哪些预训练任务？", None),
        ("论文中的模型是什么？", None),
        ("你是什么模型？并解释BERT", None),
        ("你好，请检索论文中的模型", None),
    ],
)
def test_exact_rule_routing(question, topic):
    assert system_information_topic(question) == topic


def test_system_questions_read_real_saved_config_without_retrieval_or_model(
    tmp_path, monkeypatch
):
    root, db, _version = store(tmp_path)
    work = Workbench(db, root, HybridSearch(db, root))

    def forbidden(*args, **kwargs):
        raise AssertionError("system question invoked retrieval or generation")

    monkeypatch.setattr(work.search, "search", forbidden)
    monkeypatch.setattr(work.generation, "require", forbidden)
    with protocol_server() as (url, calls, _state):
        config = work.generation.providers.save(
            values(url, model="actual-saved-fixture-model", enable_for_documents=False),
            "",
        )
        run = work.create_answer(
            "你是什么模型？", [], None, "generative", "hybrid", provider_id=config["id"]
        )
        work.run_answer(run["id"])
        answer = work.answers(run_id=run["id"])[0]
        assert (
            answer["status"] == "completed"
            and answer["result"]["kind"] == "system_info"
        )
        assert "actual-saved-fixture-model" in answer["result"]["text"]
        assert answer["result"]["configuration"]["credential_available"] is False
        assert (
            answer["claims"] == []
            and answer["evidence"] == []
            and answer["scope"] == []
        )
        assert calls == [] and work.generation.generator is None
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO app_settings VALUES('active_index',?,'test')",
            (
                json.dumps(
                    {
                        "fingerprint": {"model": "explicit-embedding-config-fixture"},
                        "chunks": 0,
                        "backend": "sqlite-vec",
                        "generation": "saved-generation",
                        "chunk_fingerprint": "not-built",
                        "relative_path": "unused",
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO app_settings VALUES('generator',?,'test')",
            (
                json.dumps(
                    {
                        "directory": "not-loaded",
                        "fingerprint": {"model": "explicit-local-config-fixture"},
                    }
                ),
            ),
        )
    for question, mode, model in [
        (
            "现在使用什么Embedding模型？",
            "extractive",
            "explicit-embedding-config-fixture",
        ),
        ("当前生成模型是什么？", "generative", "explicit-local-config-fixture"),
        ("你是什么模型？", "extractive", "原文摘录"),
    ]:
        run = work.create_answer(question, [], None, mode, "keyword")
        work.run_answer(run["id"])
        answer = work.answers(run_id=run["id"])[0]
        assert answer["status"] == "completed" and model in answer["result"]["text"]
        assert not answer["evidence"] and not answer["model_history"]


def test_literature_still_retrieves_and_system_context_is_excluded(
    tmp_path, monkeypatch
):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    conversation = work.create_conversation()["id"]
    system = work.create_answer(
        "你是什么模型？", [], None, "extractive", "keyword", conversation
    )
    work.run_answer(system["id"])
    calls = []
    real_search = work.search.search

    def spy(query, *args, **kwargs):
        calls.append(query)
        return real_search(query, *args, **kwargs)

    monkeypatch.setattr(work.search, "search", spy)
    run = work.create_answer(
        "BERT 使用了哪些预训练任务？",
        [version],
        None,
        "extractive",
        "keyword",
        conversation,
    )
    work.run_answer(run["id"])
    answer = work.answers(run_id=run["id"])[0]
    assert calls == ["BERT 使用了哪些预训练任务？"]
    assert answer["evidence"] and answer["result"]["intent"] == "literature"
    assert answer["result"]["retrieval_status"] == "hits"
    assert answer["result"]["context_policy"]["turns"] == 0
    empty = work.create_answer(
        "zzzz_unknown_94783562", [version], None, "extractive", "keyword"
    )
    work.run_answer(empty["id"])
    assert work.answers(run_id=empty["id"])[0]["evidence"] == []
    assert (
        work.answers(run_id=empty["id"])[0]["result"]["retrieval_status"] == "no_hits"
    )


def test_system_api_allows_empty_scope_but_literature_does_not(tmp_path):
    root, _db, _version = store(tmp_path)
    with TestClient(
        create_app("c" * 64, root),
        base_url="http://127.0.0.1",
        headers={"X-RAG-Session": "c" * 64},
    ) as client:
        body = {
            "question": "你是什么模型？",
            "mode": "extractive",
            "strategy": "keyword",
        }
        run = client.post("/v0/answers", json=body)
        assert run.status_code == 202
        answer = client.get("/v0/answers/" + run.json()["id"]).json()
        assert answer["result"]["kind"] == "system_info" and not answer["evidence"]
        assert (
            client.post(
                "/v0/answers", json={**body, "question": "BERT pretraining"}
            ).json()["code"]
            == "SCOPE_NOT_AVAILABLE"
        )
        health = client.get("/v0/health").json()
        assert health["api_revision"] == "0.5-local" and health["system_question_forms"]
