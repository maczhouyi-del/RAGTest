"""Real SQLite/PDF persistence, protocol fixtures are not scientific gold."""

import json

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.models.provider_registry import ProviderRegistry
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database
from ragsystem.workflows.history import History
from ragsystem.workflows.workbench import Workbench
from test_generation_providers import protocol_server, values
from test_mvp_core import store


def test_three_turn_context_paging_restart_isolation_and_failure(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    conversation = work.create_conversation()["id"]
    with protocol_server() as (url, calls, state):
        config = work.generation.providers.save(values(url), "session-test-key")
        ids = []
        for question in [
            "BERT pre-training tasks",
            "How do these two tasks differ?",
            "Did the authors verify their importance?",
        ]:
            run = work.create_answer(
                question,
                [version],
                None,
                "generative",
                "keyword",
                conversation,
                config["id"],
                True,
                config["revision"],
            )
            ids.append(run["id"])
            work.run_answer(run["id"])
            detail = History(work).answer(run["id"], None)
            assert detail["status"] == "completed" and detail["evidence"]
            assert detail["conversation_id"] == conversation
        assert History(work).conversations()["total"] == 1
        answer_inputs = [
            json.loads(body["messages"][1]["content"])
            for _, body, _ in calls
            if body and "entire claim" not in body["messages"][0]["content"]
        ]
        assert len(answer_inputs[1]["conversation_context_not_evidence"]) == 1
        assert (
            "BERT pre-training tasks"
            in answer_inputs[1]["conversation_context_not_evidence"][0]["question"]
        )
        assert (
            "BERT"
            in History(work).answer(ids[1], None)["result"]["context_policy"][
                "retrieval_query"
            ]
        )
        assert all(
            "citation_id" not in turn
            for turn in answer_inputs[2]["conversation_context_not_evidence"]
        )
        state["forged"] = True
        failed = work.create_answer(
            "BERT failure",
            [version],
            None,
            "generative",
            "keyword",
            conversation,
            config["id"],
            True,
            config["revision"],
        )
        work.run_answer(failed["id"])
        assert History(work).answer(failed["id"], None)["status"] == "failed"
    restarted = Workbench(Database(db.path), root, HybridSearch(db, root))
    history = History(restarted)
    first = history.turns(conversation, limit=2)
    second = history.turns(conversation, cursor=first["next_cursor"], limit=2)
    assert first["total"] == 4 and second["next_cursor"] is None
    assert [r["id"] for r in second["items"] + first["items"]] == ids + [failed["id"]]
    assert history.conversations()["total"] == 1
    another = restarted.create_conversation()["id"]
    assert history.turns(another)["total"] == 0
    assert history.conversations(limit=1)["items"][0]["id"] == another
    assert (
        history.conversations(cursor=history.conversations(limit=1)["next_cursor"])[
            "items"
        ][0]["id"]
        == conversation
    )
    with pytest.raises(EngineError, match="NOT_FOUND"):
        history.turns(conversation, project_id="different-project")
    assert ProviderRegistry(db).list()[0]["configured"] is False
    assert db.integrity()["foreign_key_check"] == []


def test_context_is_bounded_and_pending_turn_prevents_duplicate(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    conversation = work.create_conversation()["id"]
    for i in range(5):
        run = work.create_answer(
            "BERT " + str(i) + " x" * 1000,
            [version],
            None,
            "extractive",
            "keyword",
            conversation,
        )
        with pytest.raises(EngineError, match="CONVERSATION_BUSY"):
            work.create_answer(
                "BERT repeat", [version], None, "extractive", "keyword", conversation
            )
        work.run_answer(run["id"])
    with db.connection() as conn:
        context = work.conversation_context(conn, conversation)
    assert len(context) == 3
    assert (
        sum(len(v["question"]) + len(v["answer_context_not_evidence"]) for v in context)
        <= 1600
    )


def test_v14_migration_preserves_legacy_conversation_and_snapshot(tmp_path):
    import hashlib
    import sqlite3
    from pathlib import Path

    from ragsystem.storage.database import utc_now

    path = tmp_path / "research.db"
    migrations = (
        Path(__file__).resolve().parents[2] / "engine/ragsystem/storage/migrations"
    )
    with sqlite3.connect(path) as conn:
        for script in sorted(migrations.glob("*.sql")):
            number = int(script.name.split("_")[0])
            if number > 14:
                continue
            text = script.read_text()
            conn.executescript(text)
            conn.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (number, hashlib.sha256(text.encode()).hexdigest(), utc_now()),
            )
            conn.execute(f"PRAGMA user_version={number}")
        conn.execute(
            "INSERT INTO conversations VALUES('legacy','Legacy single question',NULL,?)",
            (utc_now(),),
        )
    db = Database(path)
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id='legacy'").fetchone()
        assert (
            row["title"] == "Legacy single question"
            and row["updated_at"] == row["created_at"]
        )
    snapshots = list((tmp_path / "migration-backups").glob("before-v14-*.db"))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 14
        assert (
            conn.execute(
                "SELECT title FROM conversations WHERE id='legacy'"
            ).fetchone()[0]
            == "Legacy single question"
        )
