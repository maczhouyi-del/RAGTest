import json
import sqlite3
import struct
from pathlib import Path

from ragsystem.domain.errors import EngineError
from ragsystem.vector_adapters.base import ExactAdapter


class SQLiteVec(ExactAdapter):
    def __init__(self, path: Path, space_id: str, dimension: int, metric="cosine"):
        super().__init__(space_id, dimension, metric)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config = json.dumps([space_id, dimension, metric])
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS adapter_config(value TEXT PRIMARY KEY)")
            existing = conn.execute("SELECT value FROM adapter_config").fetchone()
            if existing and existing[0] != self.config:
                raise EngineError("SPACE_MISMATCH")
            conn.execute("INSERT OR IGNORE INTO adapter_config VALUES(?)", (self.config,))
            conn.execute(
                "CREATE TABLE IF NOT EXISTS vectors(embedding_id TEXT PRIMARY KEY,vector BLOB NOT NULL)"
            )

    def _connect(self):
        from contextlib import contextmanager

        @contextmanager
        def open_connection():
            import sqlite_vec

            conn = sqlite3.connect(self.path)
            try:
                conn.enable_load_extension(True)
                try:
                    sqlite_vec.load(conn)
                finally:
                    conn.enable_load_extension(False)
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()

        return open_connection()

    def upsert(self, entries):
        entries = list(entries)
        self.validate_ids([i for i, _ in entries])
        encoded = [
            (i, struct.pack("<" + "f" * self.dimension, *self.vector(v))) for i, v in entries
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO vectors VALUES(?,?) ON CONFLICT(embedding_id) DO UPDATE SET vector=excluded.vector",
                encoded,
            )

    def delete(self, ids):
        self.validate_ids(ids)
        with self._connect() as conn:
            conn.executemany("DELETE FROM vectors WHERE embedding_id=?", [(i,) for i in ids])

    def ids(self):
        with self._connect() as conn:
            return {row[0] for row in conn.execute("SELECT embedding_id FROM vectors")}

    def search_exact(self, query, eligible_embedding_ids, k):
        eligible = sorted(set(eligible_embedding_ids))
        vector = self.validate_query(query, eligible, k)
        if not eligible:
            return []
        function = "vec_distance_cosine" if self.metric == "cosine" else "vec_distance_l2"
        with self._connect() as conn:
            conn.execute("CREATE TEMP TABLE eligible(embedding_id TEXT PRIMARY KEY)")
            conn.executemany("INSERT INTO eligible VALUES(?)", [(i,) for i in eligible])
            # A literal WHERE eligibility constraint is evaluated before Top-K.
            rows = conn.execute(
                f"SELECT v.embedding_id,{function}(v.vector,?) AS distance FROM vectors v JOIN eligible e ON e.embedding_id=v.embedding_id ORDER BY distance,v.embedding_id LIMIT ?",
                [struct.pack("<" + "f" * self.dimension, *vector), k],
            ).fetchall()
        return [{"embedding_id": i, "distance": float(distance)} for i, distance in rows]

    def rebuild(self, entries):
        entries = list(entries)
        self.validate_ids([i for i, _ in entries])
        data = [(i, struct.pack("<" + "f" * self.dimension, *self.vector(v))) for i, v in entries]
        with self._connect() as conn:
            conn.execute("DELETE FROM vectors")
            conn.executemany("INSERT INTO vectors VALUES(?,?)", data)
        return self.check_integrity([i for i, _ in entries])
