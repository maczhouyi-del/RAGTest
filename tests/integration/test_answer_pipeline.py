"""Answer-boundary engineering fixtures, never human scientific validation."""

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.library.identity import Identity
from ragsystem.library.lifecycle import Lifecycle
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.workflows.workbench import Workbench
from test_mvp_core import ROOT, store


@pytest.fixture
def work(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    return Workbench(db, root, HybridSearch(db, root)), version


def ask(work, version, question="BERT pre-training", mode="extractive", conversation=None):
    run = work.create_answer(question, [version], None, mode, "keyword", conversation)
    work.run_answer(run["id"])
    return work.answers(run_id=run["id"])[0]


class GeneratorFixture:
    fingerprint = {"fixture": "answer-boundary-only"}

    def __init__(self, state="supported", before_output=lambda: None):
        self.state, self.before_output, self.calls = state, before_output, []

    def generate(self, task, data):
        self.calls.append((task, data))
        if self.state == "failure":
            raise EngineError("MODEL_TIMEOUT")
        if task == "support":
            return {
                "status": "supported" if self.state == "invalid_conditions" else self.state,
                "reason": "engineering fixture; not science",
            }
        self.before_output()
        first = data["chunks"][0]
        evidence = {"chunk_id": first["chunk_id"], "quote": first["text"][:60]}
        if self.state == "forged":
            evidence["chunk_id"] = "another-turn-or-invented-chunk"
        elif self.state == "mismatch":
            evidence["quote"] = "INVENTED QUOTE 94783562"
        claim = {"text": "Engineering fixture claim", "evidence": [evidence]}
        if self.state == "invalid_conditions":
            claim["conditions"] = []
        return {"claims": [claim]}


def test_default_quota_is_three_even_for_one_paper(work):
    bench, version = work
    answer = ask(bench, version)
    assert answer["status"] == "completed" and len(answer["evidence"]) == 3
    assert answer["result"]["retrieval"]["per_paper_limit"] == 3
    assert len(answer["result"]["retrieval"]["hits"]) == 3


def test_quota_follows_confirmed_logical_paper_merge(work):
    bench, one = work
    two = PdfImporter(bench.db, bench.root).import_path_for_test(
        ROOT / "tests/fixtures/public/2020.emnlp-main.550.pdf", "second"
    )["doc_version_id"]
    Parser(bench.db, bench.root).parse(two, "parse-second")
    hits = bench.search.search("model", [one, two], 8, None, "keyword", 3)["results"]
    assert len(hits) <= 8 and {hit["doc_version_id"] for hit in hits} == {one, two}
    assert all(sum(hit["doc_version_id"] == version for hit in hits) <= 3 for version in (one, two))
    docs = {row["doc_version_id"]: row["document_id"] for row in Library(bench.db).list_documents()}
    Identity(bench.db).merge(docs[one], docs[two], [one, two])
    merged = bench.search.search("model", [one, two], 8, None, "keyword", 3)["results"]
    assert len(merged) == 3
    assert all(
        bench.sources.anchor(hit["source_anchor_id"])["doc_version_id"] == hit["doc_version_id"]
        for hit in merged
    )


def test_independent_question_does_not_inherit_previous_query(work, monkeypatch):
    bench, version = work
    first = ask(bench, version)
    calls = []
    original = bench.search.search

    def search(query, *args, **kwargs):
        calls.append(query)
        return original(query, *args, **kwargs)

    monkeypatch.setattr(bench.search, "search", search)
    current = ask(bench, version, "zzzz_unknown_94783562", conversation=first["conversation_id"])
    assert calls == ["zzzz_unknown_94783562"]
    assert current["result"]["outcome"] == "no_hits" and current["evidence"] == []
    assert current["result"]["context_policy"]["strategy"] == "current_question_only"
    followup = ask(bench, version, "继续比较它们", conversation=first["conversation_id"])
    assert followup["result"]["context_policy"]["strategy"] == "explicit_reference_last_two"
    assert "BERT" in followup["result"]["context_policy"]["retrieval_query"]


@pytest.mark.parametrize(
    "state,status,outcome,code",
    [
        ("supported", "completed", "answered", None),
        ("uncertain", "refused", "insufficient_evidence", "INSUFFICIENT_EVIDENCE"),
        ("contradicted", "refused", "insufficient_evidence", "INSUFFICIENT_EVIDENCE"),
        ("failure", "failed", "generation_failed", "MODEL_TIMEOUT"),
        ("forged", "failed", "generation_failed", "MODEL_CITATION_INVALID"),
        ("mismatch", "failed", "generation_failed", "MODEL_CITATION_INVALID"),
        ("invalid_conditions", "failed", "generation_failed", "MODEL_OUTPUT_INVALID"),
    ],
)
def test_outcomes_and_exact_current_citation_pool(work, monkeypatch, state, status, outcome, code):
    bench, version = work
    generator = GeneratorFixture(state)
    monkeypatch.setattr(bench.generation, "require", lambda: generator)
    answer = ask(bench, version, mode="generative")
    assert (answer["status"], answer["error_code"]) == (status, code)
    assert answer["result"]["outcome"] == outcome
    assert answer["result"]["retrieval_status"] == "hits"
    assert answer["result"]["retrieval"]["hits"]
    if status == "failed":
        assert answer["claims"] == [] and answer["evidence"] == []
        assert answer["result"]["support_checks"] == []
        assert answer["result"]["claim_details"] == []
    else:
        assert answer["claims"][0]["human_status"] == "unreviewed"
        assert answer["claims"][0]["source_status"] == "verified"
        assert answer["claims"][0]["model_support"] == state


def test_no_hits_never_calls_generator(work, monkeypatch):
    bench, version = work
    generator = GeneratorFixture("failure")
    monkeypatch.setattr(bench.generation, "require", lambda: generator)
    answer = ask(bench, version, "zzzz_unknown_94783562", mode="generative")
    assert answer["result"]["outcome"] == "no_hits" and answer["status"] == "refused"
    assert generator.calls == [] and not answer["evidence"] and not answer["model_history"]


def test_retrieval_failure_preserves_query_policy_and_does_not_infer(work, monkeypatch):
    bench, version = work
    generator = GeneratorFixture()
    monkeypatch.setattr(bench.generation, "require", lambda: generator)
    run = bench.create_answer("BERT", [version], None, "generative", "hybrid")
    bench.run_answer(run["id"])
    answer = bench.answers(run_id=run["id"])[0]
    assert answer["status"] == "failed" and answer["error_code"] == "EMBEDDING_NOT_CONFIGURED"
    assert answer["result"]["outcome"] == "retrieval_failed"
    assert answer["result"]["context_policy"]["retrieval_query"] == "BERT"
    assert generator.calls == []


def test_relevance_experiment_never_uses_selected_network_provider(work, monkeypatch):
    from test_generation_providers import protocol_server, values

    bench, version = work
    with protocol_server() as (url, calls, _state):
        provider = bench.generation.providers.save(values(url), "session-fixture-key")
        run = bench.create_answer(
            "BERT",
            [version],
            None,
            "generative",
            "keyword_review",
            provider_id=provider["id"],
            provider_revision=provider["revision"],
        )
        bench.run_answer(run["id"])
        answer = bench.answers(run_id=run["id"])[0]
        assert answer["status"] == "failed" and answer["error_code"] == "GENERATOR_NOT_CONFIGURED"
        assert answer["result"]["failure_stage"] == "relevance_review"
        assert calls == []


@pytest.mark.parametrize("change", ["reparse", "retract", "archive", "unlink"])
def test_source_change_during_generation_never_publishes_old_evidence(work, monkeypatch, change):
    bench, version = work
    document = Library(bench.db).list_documents()[0]["document_id"]
    library = Library(bench.db)
    project = library.create_project("frozen project")
    library.set_membership(project["id"], document, True)

    def changed():
        if change == "reparse":
            Parser(bench.db, bench.root).parse(version, "changed")
        elif change == "unlink":
            library.set_membership(project["id"], document, False)
        else:
            Lifecycle(bench.db).update(
                document,
                0,
                "retracted" if change == "retract" else "archived",
                "injected source change",
            )

    monkeypatch.setattr(
        bench.generation, "require", lambda: GeneratorFixture(before_output=changed)
    )
    run = bench.create_answer("BERT", [version], project["id"], "generative", "keyword")
    bench.run_answer(run["id"])
    answer = bench.answers(project["id"], run_id=run["id"])[0]
    assert answer["status"] == "failed" and not answer["evidence"] and not answer["claims"]
    assert answer["error_code"] in {"SCOPE_STALE", "SCOPE_NOT_AVAILABLE"}


def test_new_generation_does_not_overwrite_human_review(work, monkeypatch):
    bench, version = work
    monkeypatch.setattr(bench.generation, "require", lambda: GeneratorFixture())
    first = ask(bench, version, mode="generative")
    claim = first["claims"][0]
    bench.review(claim["id"], "confirmed", "manual engineering check")
    next_answer = ask(bench, version, mode="generative", conversation=first["conversation_id"])
    original = bench.answers(run_id=first["id"])[0]
    assert original["claims"][0]["human_status"] == "confirmed"
    assert next_answer["claims"][0]["id"] != claim["id"]
    assert next_answer["claims"][0]["human_status"] == "unreviewed"
