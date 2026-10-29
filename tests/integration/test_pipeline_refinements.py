"""RAG-02 pipeline regressions. Protocol/term fixtures are not scientific gold."""

import json

import pytest
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.library.lifecycle import Lifecycle
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.retrieval.source_search import Sources
from ragsystem.retrieval.tokenizer import index_terms
from ragsystem.workflows.system_information import question_parts
from ragsystem.workflows.workbench import Workbench
from test_generation_providers import protocol_server, values
from test_mvp_core import ROOT, store


@pytest.mark.parametrize(
    "question,expected",
    [
        (
            "你是什么模型？并解释并行训练与 BERT and GPT-2 的比较，参数10 mg/mL？",
            "解释并行训练与 BERT and GPT-2 的比较，参数10 mg/mL",
        ),
        ("当前是什么模型并解释并行算法", "解释并行算法"),
        ("比较 BERT and GPT 的并行方法，当前是什么模型？", "比较 BERT and GPT 的并行方法"),
    ],
)
def test_mixed_intent_preserves_scientific_conjunctions_and_punctuation(question, expected):
    topics, literature = question_parts(question)
    assert topics == ["generation"] and literature == expected


def test_impersonal_it_is_not_a_conversation_reference():
    question = "Is it possible to use BERT for retrieval?"
    context, policy = Workbench.retrieval_context(
        question, [{"question": "unrelated battery chemistry"}]
    )
    assert context == [] and policy["retrieval_query"] == question


@pytest.fixture
def work(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    return Workbench(db, root, HybridSearch(db, root)), version


def test_new_document_scope_never_includes_old_scope_history_in_api_payload(work):
    bench, one = work
    two = PdfImporter(bench.db, bench.root).import_path_for_test(
        ROOT / "tests/fixtures/public/2020.emnlp-main.550.pdf", "two"
    )["doc_version_id"]
    Parser(bench.db, bench.root).parse(two, "parse-two")
    old = bench.create_answer("BERT pretraining", [one], None, "extractive", "keyword")
    bench.run_answer(old["id"])
    with protocol_server() as (url, calls, _state):
        provider = bench.generation.providers.save(values(url), "session-fixture-key")
        current = bench.create_answer(
            "Does it use a model?",
            [two],
            None,
            "generative",
            "keyword",
            old["conversation_id"],
            provider["id"],
            True,
            provider["revision"],
        )
        bench.run_answer(current["id"])
        result = bench.answers(run_id=current["id"])[0]
        assert result["status"] == "completed"
        assert result["result"]["context_policy"]["retrieval_query"] == "Does it use a model?"
        body = next(body for _, body, _ in calls if body)
        payload = json.loads(body["messages"][1]["content"])
        assert payload["conversation_context_not_evidence"] == []


@pytest.mark.parametrize("when", ["after_retrieval", "after_answer"])
def test_source_revocation_stops_next_model_request(work, monkeypatch, when):
    bench, version = work
    document = Library(bench.db).list_documents()[0]["document_id"]

    def revoke():
        Lifecycle(bench.db).update(document, 0, "retracted", "injected source revocation")

    if when == "after_retrieval":
        search = bench.search.search

        def retrieve(*args, **kwargs):
            result = search(*args, **kwargs)
            revoke()
            return result

        monkeypatch.setattr(bench.search, "search", retrieve)
    else:
        require = bench.generation.require

        def selected(*args, **kwargs):
            generator = require(*args, **kwargs)
            generate = generator.generate

            def generate_and_revoke(task, data):
                result = generate(task, data)
                if task == "answer":
                    revoke()
                return result

            generator.generate = generate_and_revoke
            return generator

        monkeypatch.setattr(bench.generation, "require", selected)
    with protocol_server() as (url, calls, _state):
        provider = bench.generation.providers.save(values(url), "session-fixture-key")
        run = bench.create_answer(
            "BERT",
            [version],
            None,
            "generative",
            "keyword",
            provider_id=provider["id"],
            provider_revision=provider["revision"],
        )
        bench.run_answer(run["id"])
        answer = bench.answers(run_id=run["id"])[0]
        assert answer["status"] == "failed" and not answer["evidence"] and not answer["claims"]
        assert answer["error_code"] == "SCOPE_NOT_AVAILABLE"
        assert len([body for _, body, _ in calls if body]) == (
            0 if when == "after_retrieval" else 1
        )


def test_explicit_quoted_phrase_precedes_or_noise_without_changing_source_text(work):
    bench, version = work
    texts = ["alpha beta reference", "what does beta alpha mean", "what does alpha mean"]
    with bench.db.transaction() as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM chunks ORDER BY id LIMIT 3")]
        for chunk, text in zip(ids, texts, strict=True):
            conn.execute("UPDATE chunks SET clean_text=? WHERE id=?", (text, chunk))
            conn.execute("UPDATE chunks_fts SET clean_text=? WHERE chunk_id=?", (text, chunk))
            conn.execute("DELETE FROM chunks_terms_v2 WHERE chunk_id=?", (chunk,))
            conn.execute("DELETE FROM terms_indexed_chunks_v2 WHERE chunk_id=?", (chunk,))
            index_terms(conn, chunk, text)
    source = Sources(bench.db, bench.root)
    hits = source.search('what does "alpha beta" mean', [version], 3, terms=True)
    assert hits[0]["chunk_id"] == ids[0] and hits[0]["preview"] == texts[0]
    assert hits[0]["lexical_stage"] == "quoted_phrase"
    assert ids[1] in {hit["chunk_id"] for hit in hits}
    assert [hit["lexical_rank"] for hit in hits] == list(range(1, len(hits) + 1))


def test_review_rescues_candidate_beyond_original_top_eight_and_final_quota_holds(work):
    bench, version = work
    candidates = bench.search.search(
        "BERT", [version], 8, None, "keyword", 3, include_candidates=True
    )
    target = candidates["candidates"][9]
    assert target["chunk_id"] not in {hit["chunk_id"] for hit in candidates["results"]}

    class Reviewer:
        fingerprint = {"fixture": "review-pipeline-only"}

        def generate(self, task, data):
            assert task == "relevance" and len(data["candidates"]) <= 6
            return {
                "scores": [
                    {
                        "candidate_id": item["candidate_id"],
                        "score": 5 if item["text"] == target["preview"][:500] else 0,
                        "reason": "synthetic score, no quality claim",
                    }
                    for item in data["candidates"]
                ]
            }

    bench.generation.generator = Reviewer()
    run = bench.create_answer("BERT", [version], None, "extractive", "keyword_review")
    bench.run_answer(run["id"])
    answer = bench.answers(run_id=run["id"])[0]
    assert answer["status"] == "completed"
    assert target["chunk_id"] in {item["source_anchor_id"] for item in answer["evidence"]}
    assert len(answer["evidence"]) <= 3
    assert answer["result"]["pipeline_trace"]["model_attempts"] == {
        "relevance": 2,
        "answer": 0,
        "support": 0,
    }
    review = answer["result"]["relevance_review"]
    assert target["chunk_id"] in review["final_context_chunk_ids"]
    assert target["chunk_id"] not in review["original_context_chunk_ids"]


def test_claim_cannot_cite_a_retrieved_chunk_dropped_from_actual_model_input(work, monkeypatch):
    bench, version = work
    calls = []

    class Generator:
        fingerprint = {"fixture": "dropped-input-citation-only"}

        def generate(self, task, data):
            calls.append(task)
            assert task == "answer"
            first, last = data["chunks"][0], data["chunks"][-1]
            return {
                "claims": [
                    {
                        "text": "fixture",
                        "evidence": [{"chunk_id": last["chunk_id"], "quote": last["text"][:60]}],
                    }
                ],
                "context_metadata": {
                    "included_chunk_ids": [first["chunk_id"]],
                    "dropped_chunk_ids": [last["chunk_id"]],
                },
            }

    monkeypatch.setattr(bench.generation, "require", lambda: Generator())
    run = bench.create_answer("BERT", [version], None, "generative", "keyword")
    bench.run_answer(run["id"])
    answer = bench.answers(run_id=run["id"])[0]
    assert answer["status"] == "failed" and answer["error_code"] == "MODEL_CITATION_INVALID"
    assert calls == ["answer"] and not answer["claims"] and not answer["evidence"]


def test_quote_must_be_inside_the_actual_sent_excerpt_not_only_the_same_chunk(work, monkeypatch):
    bench, version = work
    tasks = []

    class Generator:
        fingerprint = {"fixture": "excerpt-boundary-only"}

        def generate(self, task, data):
            tasks.append(task)
            assert task == "answer"
            chunk = data["chunks"][0]
            # The quoted text exists in the same retrieved chunk, beyond the
            # claimed actual model input. Publishing it would invent provenance.
            return {
                "claims": [
                    {
                        "text": "fixture",
                        "evidence": [
                            {"chunk_id": chunk["chunk_id"], "quote": chunk["text"][80:100]}
                        ],
                    }
                ],
                "context_metadata": {
                    "included_chunk_ids": [chunk["chunk_id"]],
                    "excerpt_lengths": [
                        {
                            "chunk_id": chunk["chunk_id"],
                            "original_characters": len(chunk["text"]),
                            "included_characters": 40,
                            "is_partial": True,
                        }
                    ],
                },
            }

    monkeypatch.setattr(bench.generation, "require", lambda: Generator())
    run = bench.create_answer("BERT", [version], None, "generative", "keyword")
    bench.run_answer(run["id"])
    answer = bench.answers(run_id=run["id"])[0]
    assert answer["status"] == "failed" and answer["error_code"] == "MODEL_CITATION_INVALID"
    assert tasks == ["answer"] and not answer["claims"]
    trace = answer["result"]["pipeline_trace"]
    assert trace["stages"][-1]["status"] == "failed"
    assert trace["model_attempts"] == {"answer": 1, "support": 0, "relevance": 0}
