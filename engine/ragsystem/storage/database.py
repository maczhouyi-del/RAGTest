import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from ragsystem.domain.errors import EngineError

SCHEMA_VERSION = 15


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        scripts = sorted(
            files("ragsystem").joinpath("storage/migrations").iterdir(), key=lambda p: p.name
        )
        migrations = [
            (int(p.name.split("_", 1)[0]), p.read_text())
            for p in scripts
            if p.name.endswith(".sql")
        ]
        with self.connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise EngineError("SCHEMA_TOO_NEW")
            if 0 < version < SCHEMA_VERSION:
                backup_dir = self.path.parent / "migration-backups"
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f"before-v{version}-{uuid4()}.db"
                with sqlite3.connect(backup_path) as backup:
                    conn.backup(backup)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Recheck after taking the migration writer lock.
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise EngineError("SCHEMA_TOO_NEW")
                for number, script in migrations:
                    digest = hashlib.sha256(script.encode()).hexdigest()
                    if number > version:
                        for statement in script.split(";"):
                            if statement.strip():
                                conn.execute(statement)
                        conn.execute(
                            "INSERT INTO schema_migrations VALUES(?,?,?)",
                            (number, digest, utc_now()),
                        )
                        conn.execute(f"PRAGMA user_version={number}")
                    existing = conn.execute(
                        "SELECT sha256 FROM schema_migrations WHERE version=?", (number,)
                    ).fetchone()
                    if existing is None or existing[0] != digest:
                        raise EngineError("MIGRATION_FINGERPRINT_MISMATCH")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=3, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=3000")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def integrity(self) -> dict:
        with self.connection() as conn:
            return {
                "integrity_check": [row[0] for row in conn.execute("PRAGMA integrity_check")],
                "foreign_key_check": [
                    tuple(row) for row in conn.execute("PRAGMA foreign_key_check")
                ],
            }
