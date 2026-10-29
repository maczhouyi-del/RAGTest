import json
import secrets
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database
from ragsystem.workflows.workbench import Workbench

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "研究 空格"
    db = Database(root / "data/research.db")
    importer = PdfImporter(db, root)
    one = importer.import_path_for_test(ROOT / "tests/fixtures/public/N19-1423.pdf", "one")[
        "doc_version_id"
    ]
    two = importer.import_path_for_test(
        ROOT / "tests/fixtures/public/2020.emnlp-main.550.pdf", "two"
    )["doc_version_id"]
    Parser(db, root).parse(one, "parse")
    return root, db, one, two


class StructuredFixtureGenerator:
    """Engineering response fixture only, never a scientific model/gold evaluation."""

    fingerprint = {"fixture": "engineering-only"}

    def generate(self, task, data):
        if task == "support":
            return {"status": "uncertain", "reason": "fixture cannot certify scientific support"}
        chunk = data["chunks"][0]
        return {
            "claims": [
                {
                    "text": "Fixture draft",
                    "evidence": [{"chunk_id": chunk["chunk_id"], "quote": chunk["text"][:60]}],
                }
            ]
        }


def test_extractive_source_contract_review_scope_and_stale_parse(store):
    root, db, one, two = store
    work = Workbench(db, root, HybridSearch(db, root))
    project = Library(db).create_project("项目甲")
    with pytest.raises(EngineError, match="SCOPE_NOT_AVAILABLE"):
        work.create_answer("BERT", [one], project["id"], "extractive", "keyword")
    doc = next(row for row in Library(db).list_documents() if row["doc_version_id"] == one)
    Library(db).set_membership(project["id"], doc["document_id"], True)
    answer = work.create_answer("BERT pretraining", [one], project["id"], "extractive", "keyword")
    work.run_answer(answer["id"])
    run = work.answers(project["id"])[0]
    assert run["status"] == "completed" and run["claims"] == []
    assert run["scope"][0]["parse_run_ids"] and run["result"]["kind"] == "evidence_only"
    evidence = run["evidence"][0]
    schema = json.loads((ROOT / "contracts/evidence-span.schema.json").read_text())
    jsonschema.validate(evidence["span"], schema)
    assert (
        evidence["span"]["clean_text_offsets"]["end"]
        > evidence["span"]["clean_text_offsets"]["start"]
    )
    work.review(evidence["id"], "confirmed", "原文核对")
    work.review(evidence["id"], "rejected", "纠正")
    with db.connection() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM human_reviews WHERE target_id=?", (evidence["id"],)
            ).fetchone()[0]
            == 2
        )
    assert work.answers(None) == []
    with pytest.raises(EngineError, match="RESEARCH_REQUIRED"):
        work.create_answer("Summarize all papers", [one], None, "extractive", "keyword")
    Parser(db, root).parse(one, "reparse")
    assert all(
        record["current_source_status"] == "stale_or_unavailable"
        for record in work.answers(project["id"])[0]["evidence"]
    )


def test_generated_draft_separates_support_and_refuses_forged_quotes_atomically(store):
    root, db, one, _ = store
    work = Workbench(db, root, HybridSearch(db, root))
    work.generation.generator = StructuredFixtureGenerator()
    answer = work.create_answer("BERT", [one], None, "generative", "keyword")
    work.run_answer(answer["id"])
    run = work.answers()[0]
    assert run["status"] == "refused" and run["claims"][0]["model_support"] == "uncertain"
    assert run["claims"][0]["comparability"] == "not_assessed"

    class Forged(StructuredFixtureGenerator):
        def generate(self, task, data):
            return {
                "claims": [
                    {
                        "text": "injected",
                        "evidence": [
                            {
                                "chunk_id": data["chunks"][0]["chunk_id"],
                                "quote": "FORGED QUOTE DOES NOT EXIST",
                            }
                        ],
                    }
                ]
            }

    work.generation.generator = Forged()
    row = work.create_answer("BERT", [one], None, "generative", "keyword")
    work.run_answer(row["id"])
    result = next(run for run in work.answers() if run["id"] == row["id"])
    assert result["status"] == "failed" and result["error_code"] == "MODEL_CITATION_INVALID"
    assert result["claims"] == result["evidence"] == []


def test_research_per_paper_coverage_revisions_report_and_unparsed_not_absence(store):
    root, db, one, two = store
    work = Workbench(db, root, HybridSearch(db, root))
    plan = work.create_plan(
        "逐篇核对", ["BERT", "nonexistent-field"], [one, two], None, "extractive"
    )
    job = Jobs(db).enqueue("research_extract", "run", {"plan_id": plan["id"]})
    work.execute_plan(plan["id"], job["id"])
    result = work.plans()[0]
    assert (
        result["status"] == "partial"
        and result["coverage"]["completed"] == 1
        and result["coverage"]["needs_parse"] == 1
    )
    item = next(item for item in result["items"] if item["doc_version_id"] == one)
    with db.connection() as conn:
        expected = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE doc_version_id=? AND visible=1", (one,)
        ).fetchone()[0]
    assert item["processed_chunks"] == item["total_chunks"] == expected > 0
    assert item["observations"] and all(
        obs["meaning_status"] == "evidence_insufficient" for obs in item["observations"]
    )
    obs = item["observations"][0]
    body = {
        "expected_revision": 0,
        "value": "人工核对的摘录",
        "unit": "",
        "experiment_id": "experiment-1",
        "meaning_status": "reported",
        "conditions_status": "unknown",
        "conditions": {"dataset": "待核对"},
    }
    work.edit_observation(plan["id"], obs["evidence_id"], body)
    with pytest.raises(EngineError, match="REVIEW_CONFLICT"):
        work.edit_observation(plan["id"], obs["evidence_id"], body)
    report = work.report(plan["id"])
    content = work.report_content(report["id"])["body"]
    assert (
        "未提取（非未报告）" in content and "needs_parse" in content and "人工核对的摘录" in content
    )
    assert work.report(plan["id"])["revision"] == 2
    assert work.report_content(report["id"])["body"] == content
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM observation_revisions").fetchone()[0] == 1
    # Completed papers are reused, not scanned or revised again on resume.
    resumed = Jobs(db).enqueue("research_extract", "resume", {"plan_id": plan["id"]})
    work.execute_plan(plan["id"], resumed["id"])
    assert (
        next(item for item in work.plans()[0]["items"] if item["doc_version_id"] == one)[
            "observations"
        ][0]["value"]
        == "人工核对的摘录"
    )


def test_partial_parse_is_not_full_paper_coverage_and_cancel_fences_publish(store, monkeypatch):
    root, db, one, _ = store
    with db.transaction() as conn:
        conn.execute("UPDATE document_versions SET parse_status='partial' WHERE id=?", (one,))
    work = Workbench(db, root, HybridSearch(db, root))
    plan = work.create_plan("BERT", ["BERT"], [one], None, "extractive")
    job = Jobs(db).enqueue("research_extract", "partial", {"plan_id": plan["id"]})
    work.execute_plan(plan["id"], job["id"])
    assert work.plans()[0]["coverage"]["partial"] == 1
    row = work.create_answer("BERT", [one], None, "extractive", "keyword")
    original = work.search.search

    def cancelled(*args):
        result = original(*args)
        Jobs(db).cancel(row["job_id"])
        return result

    monkeypatch.setattr(work.search, "search", cancelled)
    work.run_answer(row["id"])
    assert work.answers()[0]["status"] == "cancelled" and work.answers()[0]["evidence"] == []


def test_workbench_http_routes_and_strict_validation(store):
    root, db, one, _ = store
    token = secrets.token_hex(32)
    headers = {"X-RAG-Session": token}
    with TestClient(create_app(token, root), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/v0/answers",
            headers=headers,
            json={
                "question": "BERT",
                "version_ids": [one],
                "mode": "extractive",
                "strategy": "keyword",
            },
        )
        assert response.status_code == 202
        runs = client.get("/v0/answers", headers=headers).json()["answers"]
        assert runs[0]["status"] == "completed"
        assert (
            client.post(
                "/v0/answers",
                headers=headers,
                json={
                    "question": "BERT",
                    "version_ids": [one],
                    "mode": "extractive",
                    "shell": "ls",
                },
            ).status_code
            == 400
        )
        plan = client.post(
            "/v0/research",
            headers=headers,
            json={
                "question": "BERT",
                "fields": ["BERT"],
                "version_ids": [one],
                "mode": "extractive",
            },
        ).json()
        assert (
            client.post("/v0/research/" + plan["id"] + "/run", headers=headers).status_code == 202
        )
        assert (
            client.get("/v0/research", headers=headers).json()["plans"][0]["coverage"]["completed"]
            == 1
        )
        report = client.post("/v0/research/" + plan["id"] + "/reports", headers=headers)
        assert report.status_code == 201
        assert "body" in client.get("/v0/reports/" + report.json()["id"], headers=headers).json()


def test_project_removal_during_generation_is_rechecked_before_publication(store):
    root, db, one, _ = store
    library = Library(db)
    project = library.create_project("中途改变")
    document = next(row for row in library.list_documents() if row["doc_version_id"] == one)
    library.set_membership(project["id"], document["document_id"], True)

    class RemovedScope(StructuredFixtureGenerator):
        def generate(self, task, data):
            if task == "support":
                library.set_membership(project["id"], document["document_id"], False)
                return {"status": "supported", "reason": "engineering fixture only"}
            return super().generate(task, data)

    work = Workbench(db, root, HybridSearch(db, root))
    work.generation.generator = RemovedScope()
    run = work.create_answer("BERT", [one], project["id"], "generative", "keyword")
    work.run_answer(run["id"])
    result = work.answers(project["id"])[0]
    assert result["status"] == "failed" and result["error_code"] == "SCOPE_NOT_AVAILABLE"
    assert result["claims"] == result["evidence"] == []


def test_research_counts_paper_identity_once_and_warns_on_later_merge(store):
    from ragsystem.library.identity import Identity

    root, db, one, two = store
    work = Workbench(db, root, HybridSearch(db, root))
    old = work.create_plan("逐篇", ["BERT"], [one, two], None, "extractive")
    docs = {row["doc_version_id"]: row for row in Library(db).list_documents()}
    Identity(db).merge(docs[one]["document_id"], docs[two]["document_id"], [one, two])
    with pytest.raises(EngineError, match="DUPLICATE_PAPER_VERSIONS"):
        work.create_plan("逐篇", ["BERT"], [one, two], None, "extractive")
    new = work.create_plan("选择一个版本", ["BERT"], [one], None, "extractive")
    assert len(next(plan for plan in work.plans() if plan["id"] == new["id"])["scope"]) == 1
    legacy = next(plan for plan in work.plans() if plan["id"] == old["id"])
    assert len(legacy["scope_warnings"]) == 1
    report = work.report(old["id"])
    assert "不能把本报告计数作为当前去重论文数" in work.report_content(report["id"])["body"]
    job = Jobs(db).enqueue("research_extract", "identity-change", {"plan_id": old["id"]})
    work.execute_plan(old["id"], job["id"])
    result = next(plan for plan in work.plans() if plan["id"] == old["id"])
    assert (
        next(item for item in result["items"] if item["doc_version_id"] == one)["error_code"]
        == "SCOPE_IDENTITY_CHANGED"
    )


def test_research_model_provenance_survives_failed_attempt_resume_and_human_edit(store):
    root, db, one, _ = store
    work = Workbench(db, root, HybridSearch(db, root))
    plan = work.create_plan("trace", ["method"], [one], None, "generative")

    class Candidate:
        fingerprint = {"fixture": "engineering-only", "prompt_version": "first"}
        calls = 0

        def generate(self, task, data):
            self.calls += 1
            if self.calls == 2:
                raise EngineError("MODEL_OUTPUT_INVALID")
            chunk = data["chunks"][0]
            return {
                "observations": [
                    {
                        "field": "method",
                        "value": "fixture",
                        "unit": "",
                        "chunk_id": chunk["chunk_id"],
                        "quote": chunk["text"][:20],
                    }
                ]
            }

    work.generation.generator = Candidate()
    job = Jobs(db).enqueue("research_extract", "first", {"plan_id": plan["id"]})
    work.execute_plan(plan["id"], job["id"])
    first = work.plans()[0]
    assert first["items"][0]["processed_chunks"] == 1
    assert first["model_history"][0]["fingerprint"]["prompt_version"] == "first"

    class Resumed(Candidate):
        fingerprint = {"fixture": "engineering-only", "prompt_version": "second"}

        def generate(self, task, data):
            chunk = data["chunks"][0]
            return {
                "observations": [
                    {
                        "field": "method",
                        "value": "fixture",
                        "unit": "",
                        "chunk_id": chunk["chunk_id"],
                        "quote": chunk["text"][:20],
                    }
                ]
            }

    work.generation.generator = Resumed()
    job = Jobs(db).enqueue("research_extract", "second", {"plan_id": plan["id"]})
    work.execute_plan(plan["id"], job["id"])
    result = work.plans()[0]
    observations = result["items"][0]["observations"]
    assert observations[0]["model_fingerprint"]["prompt_version"] == "first"
    assert all(row["model_fingerprint"]["prompt_version"] == "second" for row in observations[1:])
    work.edit_observation(
        plan["id"],
        observations[0]["evidence_id"],
        {
            "expected_revision": 0,
            "value": "human",
            "unit": "",
            "experiment_id": "one",
            "meaning_status": "reported",
            "conditions_status": "unknown",
            "conditions": {},
        },
    )
    assert (
        work.plans()[0]["items"][0]["observations"][0]["model_fingerprint"]["prompt_version"]
        == "first"
    )
    report = work.report_content(work.report(plan["id"])["id"])["body"]
    assert "first" in report and "second" in report and "抽取模型" in report

    class Failed(Candidate):
        def generate(self, task, data):
            raise EngineError("MODEL_OUTPUT_INVALID")

    work.generation.generator = Failed()
    run = work.create_answer("BERT", [one], None, "generative", "keyword")
    work.run_answer(run["id"])
    failed = work.answers()[0]
    assert failed["status"] == "failed" and failed["result"]["kind"] == "error"
    assert failed["result"]["outcome"] == "generation_failed"
    assert failed["result"]["claims"] == [] and failed["result"]["evidence_ids"] == []
    assert failed["claims"] == [] and failed["evidence"] == []
    assert failed["model_history"][0]["fingerprint"]["prompt_version"] == "first"


def test_optional_relevance_review_is_persisted_and_never_creates_claims_in_extractive_mode(store):
    root, db, one, _ = store
    work = Workbench(db, root, HybridSearch(db, root))

    class RelevantFixture:
        fingerprint = {"fixture": "engineering-only"}

        def generate(self, task, data):
            assert task == "relevance"
            return {
                "scores": [
                    {"candidate_id": row["candidate_id"], "score": index, "reason": "fixture"}
                    for index, row in enumerate(data["candidates"])
                ]
            }

    work.generation.generator = RelevantFixture()
    created = work.create_answer("BERT", [one], None, "extractive", "keyword_review")
    work.run_answer(created["id"])
    result = work.answers()[0]
    assert result["status"] == "completed" and result["claims"] == []
    assert result["result"]["kind"] == "evidence_only"
    ranking = result["result"]["relevance_review"]
    baseline = ranking["baseline_chunk_ids"]
    assert len(baseline) == 12 and [len(batch) for batch in ranking["batches"]] == [6, 6]
    # Each fixture batch returns scores 0..5. Equal grades across the two
    # batches retain their original order, rather than fabricating 12 grades.
    expected = [baseline[index] for index in (5, 11, 4, 10, 3, 9, 2, 8, 1, 7, 0, 6)]
    assert ranking["ranked_chunk_ids"] == expected
    assert ranking["final_context_chunk_ids"] == expected[:3]
    assert result["model_history"][0]["stage"] == "relevance"
    assert len(result["evidence"]) <= 3
