import hashlib
import sqlite3
from pathlib import Path

from ragsystem.storage.database import SCHEMA_VERSION, Database


def test_v10_upgrade_retains_prior_settings_and_preupgrade_snapshot(tmp_path):
    path = tmp_path / "data/research.db"
    path.parent.mkdir()
    migrations = Path(__file__).resolve().parents[2] / "engine/ragsystem/storage/migrations"
    with sqlite3.connect(path) as conn:
        for file in sorted(migrations.glob("*.sql")):
            version = int(file.name.split("_")[0])
            if version > 10:
                break
            script = file.read_text()
            conn.executescript(script)
            conn.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?)",
                (version, hashlib.sha256(script.encode()).hexdigest(), "2026-10-24T00:00:00+00:00"),
            )
            conn.execute(f"PRAGMA user_version={version}")
        conn.execute(
            "INSERT INTO app_settings VALUES('existing-setting','{}','2026-10-24T00:00:00+00:00')"
        )
    db = Database(path)
    with db.connection() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert (
            conn.execute(
                "SELECT value_json FROM app_settings WHERE key='existing-setting'"
            ).fetchone()[0]
            == "{}"
        )
        assert conn.execute("SELECT COUNT(*) FROM table_cells").fetchone()[0] == 0
    snapshots = list((path.parent / "migration-backups").glob("before-v10-*.db"))
    assert len(snapshots) == 1
    with sqlite3.connect(snapshots[0]) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        assert (
            conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='parse_tables'").fetchone()[
                0
            ]
            == 0
        )
        assert (
            conn.execute(
                "SELECT value_json FROM app_settings WHERE key='existing-setting'"
            ).fetchone()[0]
            == "{}"
        )
    assert db.integrity()["foreign_key_check"] == []
