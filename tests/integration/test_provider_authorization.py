"""Revision-bound persisted grants; only a local protocol fixture receives excerpts."""

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.models.provider_registry import ProviderRegistry
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.workflows.workbench import Workbench
from test_generation_providers import protocol_server, values
from test_mvp_core import store


def test_authorization_revocation_revisions_restart_and_no_boolean_bypass(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    registry = work.generation.providers
    with protocol_server() as (url, calls, state):
        config = registry.save(
            values(url, enable_for_documents=False), "session-secret-not-on-disk"
        )
        with pytest.raises(EngineError, match="PROVIDER_DOCUMENT_QA_DISABLED"):
            work.create_answer(
                "BERT",
                [version],
                None,
                "generative",
                "keyword",
                provider_id=config["id"],
                provider_revision=config["revision"],
                allow_external=True,
            )
        assert calls == []
        registry.set_authorization(config["id"], config["revision"], True)
        conversation = work.create_conversation()["id"]
        for question in ["BERT pre-training tasks", "How do these tasks differ?"]:
            run = work.create_answer(
                question,
                [version],
                None,
                "generative",
                "keyword",
                conversation,
                config["id"],
                False,
                config["revision"],
            )
            work.run_answer(run["id"])
            assert work.answers(run_id=run["id"])[0]["status"] == "completed"
        assert len([c for c in calls if c[1]]) == 4
        provider = registry.require(config["id"], for_documents=True)
        registry.set_authorization(config["id"], config["revision"], False)
        before = len(calls)
        with pytest.raises(EngineError, match="PROVIDER_DOCUMENT_QA_DISABLED"):
            provider.generate(
                "answer",
                {
                    "question": "BERT",
                    "chunks": [{"chunk_id": "only", "text": "real text"}],
                },
            )
        assert len(calls) == before
        registry.set_authorization(config["id"], config["revision"], True)
        unchanged = registry.save(
            values(
                url,
                id=config["id"],
                expected_revision=config["revision"],
                enable_for_documents=None,
            ),
            "",
        )
        assert unchanged["document_qa_enabled"] and unchanged["can_answer"]
        changed = registry.save(
            values(
                url,
                id=config["id"],
                expected_revision=unchanged["revision"],
                model="changed-model",
                enable_for_documents=None,
            ),
            "",
        )
        assert changed["configured"] and not changed["can_answer"]
        with pytest.raises(EngineError, match="PROVIDER_CHANGED"):
            provider.generate("answer", {"question": "BERT", "chunks": []})
        registry.set_authorization(changed["id"], changed["revision"], True)
        restarted = ProviderRegistry(db).list()[0]
        assert (
            restarted["document_qa_enabled"]
            and not restarted["credential_available"]
            and not restarted["can_answer"]
        )
        with db.connection() as conn:
            assert "session-secret-not-on-disk" not in "\n".join(conn.iterdump())
        registry.set_authorization(changed["id"], changed["revision"], False)
        assert not ProviderRegistry(db).list()[0]["document_qa_enabled"]


def test_revoke_between_generation_and_support_sends_no_second_request(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    with protocol_server() as (url, calls, state):
        config = work.generation.providers.save(values(url), "key")
        real_require = work.generation.require

        def wrapped(identifier=None):
            provider = real_require(identifier)
            generate = provider.generate

            def intercept(task, data):
                result = generate(task, data)
                if task == "answer":
                    work.generation.providers.set_authorization(
                        config["id"], config["revision"], False
                    )
                return result

            provider.generate = intercept
            return provider

        work.generation.require = wrapped
        run = work.create_answer(
            "BERT",
            [version],
            None,
            "generative",
            "keyword",
            provider_id=config["id"],
            provider_revision=config["revision"],
        )
        work.run_answer(run["id"])
        answer = work.answers(run_id=run["id"])[0]
        assert (
            answer["status"] == "failed"
            and answer["error_code"] == "PROVIDER_DOCUMENT_QA_DISABLED"
        )
        assert len(calls) == 1 and answer["claims"] == []


def test_v17_upgrade_preserves_config_but_does_not_invent_authorization(tmp_path):
    import hashlib
    import sqlite3
    from pathlib import Path
    from uuid import uuid4

    from ragsystem.storage.database import Database, utc_now

    path = tmp_path / "legacy.db"
    migrations = (
        Path(__file__).resolve().parents[2] / "engine/ragsystem/storage/migrations"
    )
    identifier = str(uuid4())
    with sqlite3.connect(path) as conn:
        for script in sorted(migrations.glob("*.sql")):
            version = int(script.name.split("_")[0])
            if version > 17:
                continue
            body = script.read_text()
            conn.executescript(body)
            conn.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (version, hashlib.sha256(body.encode()).hexdigest(), utc_now()),
            )
            conn.execute(f"PRAGMA user_version={version}")
        conn.execute(
            "INSERT INTO generation_providers VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                "Legacy API",
                "api",
                "https://example.com/v1",
                "saved-model",
                3,
                utc_now(),
                "custom",
                "bearer",
                "json_object",
                "max_tokens",
            ),
        )
    db = Database(path)
    value = ProviderRegistry(db).list()[0]
    assert (
        value["id"] == identifier
        and value["revision"] == 3
        and value["model"] == "saved-model"
    )
    assert not value["document_qa_enabled"] and not value["can_answer"]
    assert len(list((tmp_path / "migration-backups").glob("before-v17-*.db"))) == 1
    with db.connection() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
