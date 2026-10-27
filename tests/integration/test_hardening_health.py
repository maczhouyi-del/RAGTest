import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ipc.server import create_app
from ragsystem.storage.database import SCHEMA_VERSION, Database


def health(root):
    token = "b" * 64
    with TestClient(
        create_app(token, root), base_url="http://127.0.0.1", headers={"X-RAG-Session": token}
    ) as client:
        response = client.get("/v0/health")
        assert response.status_code == 200
        return response.json()


def test_new_database_health_real_schema_and_partial_components(tmp_path):
    value = health(tmp_path)
    db = Database(tmp_path / "data/research.db")
    assert value["schema_version"] == str(db.schema_version()) == str(SCHEMA_VERSION)
    assert value["status"] == "degraded"
    assert value["components"]["engine"]["available"]
    assert value["components"]["database"]["available"]
    assert value["components"]["keyword_search"]["available"]
    assert not value["components"]["vector_search"]["available"]
    assert not value["components"]["generation"]["eligible"]
    assert value["components"]["generation"]["remote_health_checked"] is False


def test_old_upgrade_retains_data_snapshot_and_health(tmp_path):
    path = tmp_path / "data/research.db"
    path.parent.mkdir()
    scripts = Path(__file__).resolve().parents[2] / "engine/ragsystem/storage/migrations"
    with sqlite3.connect(path) as conn:
        for script in sorted(scripts.glob("*.sql")):
            version = int(script.name.split("_")[0])
            if version > 17:
                break
            text = script.read_text()
            conn.executescript(text)
            conn.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (version, hashlib.sha256(text.encode()).hexdigest(), "baseline"),
            )
            conn.execute(f"PRAGMA user_version={version}")
        conn.execute("INSERT INTO app_settings VALUES('preserved','{}','baseline')")
    value = health(tmp_path)
    assert value["schema_version"] == str(SCHEMA_VERSION)
    with Database(path).connection() as conn:
        assert (
            conn.execute("SELECT value_json FROM app_settings WHERE key='preserved'").fetchone()[0]
            == "{}"
        )
    assert list((path.parent / "migration-backups").glob("before-v17-*.db"))


def test_future_version_rejected_without_version_rewrite(tmp_path):
    path = tmp_path / "data/research.db"
    db = Database(path)
    with db.connection() as conn:
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    with pytest.raises(EngineError, match="SCHEMA_TOO_NEW"):
        create_app("c" * 64, tmp_path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION + 1
