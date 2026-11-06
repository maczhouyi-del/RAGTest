import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.models.provider_registry import ProviderRegistry
from ragsystem.storage.database import Database, utc_now
from test_generation_providers import values


def test_single_provider_save_edit_restart_and_database_constraint(tmp_path):
    db = Database(tmp_path / "research.db")
    registry = ProviderRegistry(db)
    first = registry.save(
        values("https://api.deepseek.com/v1", vendor="deepseek"), "test-key-not-secret"
    )
    for _ in range(8):
        saved = registry.save(values("https://api.deepseek.com/v1", vendor="deepseek"), "")
        assert saved["id"] == first["id"]
    edited = registry.save(
        values(
            "https://api.openai.com/v1",
            id=saved["id"],
            expected_revision=saved["revision"],
            model="updated",
            vendor="openai",
        ),
        "",
    )
    assert edited["id"] == first["id"] and not edited["credential_available"]
    with pytest.raises(EngineError, match="PROVIDER_EXISTS"):
        registry.save(values("https://another.example/v1"), "")
    for _ in range(5):
        restarted = ProviderRegistry(Database(db.path))
        assert len(restarted.list()) == 1
        assert restarted.list()[0]["id"] == first["id"]
        assert not restarted.list()[0]["configured"]
    with db.transaction() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO generation_providers SELECT 'other',name,kind,base_url,model,revision,updated_at,vendor,auth_mode,output_mode,token_parameter,NULL FROM generation_providers WHERE retired_at IS NULL"
            )
    assert b"test-key-not-secret" not in db.path.read_bytes()


def test_concurrent_initial_saves_cannot_create_duplicates(tmp_path):
    db = Database(tmp_path / "research.db")

    def save(_):
        return ProviderRegistry(db).save(values("https://api.deepseek.com/v1"), "")["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(save, range(12)))
    assert len(set(ids)) == 1 and len(ProviderRegistry(db).list()) == 1


def legacy_database(path):
    with sqlite3.connect(path) as conn:
        for script in sorted(
            (Path(__file__).resolve().parents[2] / "engine/ragsystem/storage/migrations").glob(
                "*.sql"
            )
        ):
            version = int(script.name.split("_")[0])
            if version > 18:
                continue
            body = script.read_text()
            conn.executescript(body)
            conn.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (version, hashlib.sha256(body.encode()).hexdigest(), utc_now()),
            )
            conn.execute(f"PRAGMA user_version={version}")
        ids = [str(uuid4()) for _ in range(3)]
        for n, identifier in enumerate(ids):
            conn.execute(
                "INSERT INTO generation_providers VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    f"API {n}",
                    "api",
                    f"https://api{n}.example/v1",
                    f"model{n}",
                    1,
                    f"2026-10-3{n}T00:00:00+00:00",
                    "custom",
                    "bearer",
                    "json_object",
                    "max_tokens",
                ),
            )
            conn.execute(
                "INSERT INTO generation_provider_authorizations VALUES(?,1,1,?)",
                (identifier, utc_now()),
            )
    return ids


def test_old_multiple_configs_migrate_without_loss_and_restore_fenced(tmp_path):
    path = tmp_path / "research.db"
    ids = legacy_database(path)
    db = Database(path)
    registry = ProviderRegistry(db)
    assert db.schema_version() == 21
    assert registry.list()[0]["id"] == ids[-1]
    assert len(registry.retired()) == 2
    backup = list((tmp_path / "migration-backups").glob("before-v18-*.db"))
    assert len(backup) == 1
    with sqlite3.connect(backup[0]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM generation_providers").fetchone()[0] == 3
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 18
    with pytest.raises(EngineError, match="PROVIDER_NOT_FOUND"):
        registry.set_authorization(ids[0], 1, True)
    with pytest.raises(EngineError, match="PROVIDER_CHANGED"):
        registry.restore(ids[0], 1, ids[-1], 99)
    registry._keys[ids[-1]] = "memory-test"
    value = registry.restore(ids[0], 1, ids[-1], 1)
    assert value["id"] == ids[0] and not value["configured"] and not value["document_qa_enabled"]
    assert len(registry.list()) == 1 and len(registry.retired()) == 2 and not registry._keys
    assert ProviderRegistry(Database(path)).list()[0]["id"] == ids[0]
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM generation_providers").fetchone()[0] == 3
        assert (
            conn.execute("SELECT SUM(enabled) FROM generation_provider_authorizations").fetchone()[
                0
            ]
            == 0
        )
    assert db.integrity()["foreign_key_check"] == []
