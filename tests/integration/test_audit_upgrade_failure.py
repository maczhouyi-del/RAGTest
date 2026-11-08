"""Fault injection touches a synthetic legacy DB, never the packaged migrations."""
import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest
from ragsystem.storage.database import SCHEMA_VERSION, Database, utc_now


def test_upgrade_failure_keeps_v20_data_and_recoverable_preupgrade_copy(tmp_path, monkeypatch):
    root = tmp_path/'中文 工作区'
    root.mkdir()
    path = root/'research.db'
    migrations = Path(__file__).resolve().parents[2]/'engine/ragsystem/storage/migrations'
    with sqlite3.connect(path) as conn:
        for file in sorted(migrations.glob('*.sql')):
            number = int(file.name.split('_')[0])
            if number > 20:
                break
            script = file.read_text()
            conn.executescript(script)
            conn.execute('INSERT INTO schema_migrations VALUES(?,?,?)',(number,hashlib.sha256(script.encode()).hexdigest(),utc_now()))
        conn.execute('PRAGMA user_version=20')
        conn.execute("INSERT INTO app_settings VALUES('sentinel','{}',?)",(utc_now(),))
    original = Path.read_text
    def broken(file, *args, **kwargs):
        text = original(file, *args, **kwargs)
        return text+'; INVALID SQL FAULT;' if file.parent == migrations and file.name.startswith('0021_') else text
    with monkeypatch.context() as patch:
        patch.setattr(Path,'read_text',broken)
        with pytest.raises(sqlite3.DatabaseError):
            Database(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 20
        assert conn.execute("SELECT value_json FROM app_settings WHERE key='sentinel'").fetchone()[0] == '{}'
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name='structure_publications'").fetchone()[0] == 0
    backup = next((root/'migration-backups').glob('before-v20-*.db'))
    restored = tmp_path/'恢复 副本.db'
    shutil.copyfile(backup, restored)
    recovered = Database(restored)
    assert recovered.schema_version() == SCHEMA_VERSION
    assert recovered.integrity() == {'integrity_check':['ok'],'foreign_key_check':[]}
    with recovered.connection() as conn:
        assert conn.execute("SELECT value_json FROM app_settings WHERE key='sentinel'").fetchone()[0] == '{}'
