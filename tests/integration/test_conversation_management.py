import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database, utc_now
from ragsystem.workflows.history import History
from ragsystem.workflows.workbench import Workbench
from test_mvp_core import store as make_store


@pytest.fixture
def store(tmp_path):
    root, db, version = make_store(tmp_path)
    Parser(db, root).parse(version, "parse")
    return root, db, version


def workbench(store):
    root, db, version = store
    work = Workbench(db, root, HybridSearch(db, root))
    return root, db, version, work, History(work)


def test_archive_restore_rename_pagination_restart_and_project(store):
    root, db, version, work, history = workbench(store)
    runs = [work.create_conversation() for _ in range(5)]
    with db.transaction() as conn:
        conn.execute("UPDATE conversations SET updated_at='2026-10-31T00:00:00+00:00'")
    before = history.conversations(limit=2)
    target = before["items"][0]["id"]
    history.manage_conversation(target, "rename", title="我的 BERT 对话")
    history.manage_conversation(target, "archive")
    assert history.conversations()["total"] == 4
    assert history.index("archived_conversations")["items"][0]["id"] == target
    assert history.turns(target)["conversation"]["title"] == "我的 BERT 对话"
    with pytest.raises(EngineError, match="CONVERSATION_ARCHIVED"):
        work.create_answer("你是什么模型", [], None, "extractive", "keyword", target)
    project = Library(db).create_project("独立项目")["id"]
    other = work.create_conversation(project)
    with pytest.raises(EngineError, match="NOT_FOUND"):
        history.manage_conversation(target, "delete", project)
    assert history.conversations(project)["items"][0]["id"] == other["id"]
    history.manage_conversation(target, "restore")
    ids, cursor = [], None
    while True:
        page = history.conversations(cursor=cursor, limit=2)
        ids += [r["id"] for r in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(ids) == len(set(ids)) == len(runs)
    run = work.create_answer("你是什么模型", [], None, "extractive", "keyword", target)
    work.run_answer(run["id"])
    assert history.turns(target)["conversation"]["title"] == "我的 BERT 对话"
    history.manage_conversation(target, "archive")
    restarted = Database(root / "data/research.db")
    assert (
        History(Workbench(restarted, root, HybridSearch(restarted, root))).index(
            "archived_conversations"
        )["total"]
        == 1
    )
    for item in runs:
        history.manage_conversation(item["id"], "archive")
    archived_ids, cursor = [], None
    while True:
        page = history.index("archived_conversations", cursor=cursor, limit=2)
        archived_ids.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(archived_ids) == len(set(archived_ids)) == 5
    assert history.conversations(project)["total"] == 1


def test_delete_owns_only_turn_data_and_preserves_sources_and_research(store):
    root, db, version, work, history = workbench(store)
    first = work.create_answer("BERT", [version], None, "extractive", "keyword")
    second = work.create_answer("BERT", [version], None, "extractive", "keyword")
    work.run_answer(first["id"])
    work.run_answer(second["id"])
    plan = work.create_plan("research", ["BERT"], [version], None, "extractive")
    answer = work.answers(run_id=first["id"])[0]
    evidence = answer["evidence"][0]
    work.review(evidence["id"], "confirmed", "test")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO claim_records VALUES('test-claim',?,?,?,'verified','supported','not_assessed','unreviewed')",
            (first["id"], "test", '["' + evidence["id"] + '"]'),
        )
    files = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.pdf")}
    vector = root / "index-preservation-test.bin"
    vector.write_bytes(b"explicit synthetic preservation sentinel")
    tables = [
        "documents",
        "document_versions",
        "chunks",
        "parse_runs",
        "embedding_records",
        "chunk_embedding_links",
        "index_generations",
        "research_plans",
    ]
    with db.connection() as conn:
        counts = {t: conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0] for t in tables}
    assert history.manage_conversation(first["conversation_id"], "delete")["deleted_turns"] == 1
    assert history.answer(second["id"], None)["evidence"]
    with db.connection() as conn:
        for t, n in counts.items():
            assert conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0] == n
        for table, column, identifier in [
            ("answer_runs", "id", first["id"]),
            ("claim_records", "run_id", first["id"]),
            ("evidence_records", "owner_id", first["id"]),
            ("human_reviews", "target_id", evidence["id"]),
            ("jobs", "id", first["job_id"]),
            ("events", "job_id", first["job_id"]),
            ("job_attempts", "job_id", first["job_id"]),
        ]:
            assert not conn.execute(
                f"SELECT 1 FROM {table} WHERE {column}=?", (identifier,)
            ).fetchone()
        assert conn.execute("SELECT 1 FROM research_plans WHERE id=?", (plan["id"],)).fetchone()
    assert {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.pdf")
    } == files
    assert vector.read_bytes() == b"explicit synthetic preservation sentinel"
    assert db.integrity()["foreign_key_check"] == []
    again = Database(root / "data/research.db")
    with pytest.raises(EngineError, match="NOT_FOUND"):
        History(Workbench(again, root, HybridSearch(again, root))).turns(first["conversation_id"])


def test_active_job_delete_refused_and_claim_race(store):
    _, db, version, work, history = workbench(store)
    run = work.create_answer("BERT", [version], None, "extractive", "keyword")

    def delete():
        try:
            history.manage_conversation(run["conversation_id"], "delete")
        except EngineError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        deletion = pool.submit(delete)
        claim = pool.submit(Jobs(db).claim, run["job_id"])
        assert deletion.result() == "CONVERSATION_BUSY"
        assert claim.result()["lease_token"]
    Jobs(db).cancel(run["job_id"])
    assert history.manage_conversation(run["conversation_id"], "delete")["deleted"]
    assert Jobs(db).claim(run["job_id"]) is None
    assert db.integrity()["foreign_key_check"] == []


def test_delete_refuses_evidence_still_referenced_by_research(store):
    _, db, version, work, history = workbench(store)
    run = work.create_answer("BERT", [version], None, "extractive", "keyword")
    work.run_answer(run["id"])
    evidence = history.answer(run["id"], None)["evidence"][0]
    plan = work.create_plan("research", ["BERT"], [version], None, "extractive")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO observation_revisions VALUES(?,?,?,?,1,'{}','{}','user',?)",
            ("research-reference", plan["id"], version, evidence["id"], utc_now()),
        )
    with pytest.raises(EngineError, match="CONVERSATION_REFERENCED"):
        history.manage_conversation(run["conversation_id"], "delete")
    assert history.turns(run["conversation_id"])["total"] == 1
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM observation_revisions").fetchone()[0] == 1
    assert db.integrity()["foreign_key_check"] == []


def test_manage_api_rejects_invalid_and_foreign_scope(store):
    root, _, _, work, _ = workbench(store)
    identifier = work.create_conversation()["id"]
    token = "a" * 64
    with TestClient(
        create_app(token, root), base_url="http://127.0.0.1", headers={"X-RAG-Session": token}
    ) as client:
        url = f"/v0/conversations/{identifier}/manage"
        assert client.post(url, json={"action": "rename", "title": "  "}).status_code == 400
        assert (
            client.post(url, json={"action": "archive", "project_id": "wrong"}).status_code == 404
        )
        assert client.post(url, json={"action": "archive"}).status_code == 200
        assert client.get("/v0/history/conversations").json()["total"] == 0
        assert client.get("/v0/history/archived_conversations").json()["total"] == 1
        assert client.post(url, json={"action": "restore"}).status_code == 200
        assert client.post(url, json={"action": "delete"}).status_code == 200
