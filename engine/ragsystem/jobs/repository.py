import hashlib
import json
import secrets
import time
from contextlib import nullcontext
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.storage.database import Database, utc_now


class Jobs:
    TYPES = {
        "import",
        "parse_page",
        "embed_batch",
        "index_upsert",
        "verify",
        "research_extract",
        "backup",
    }

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def event(conn, job_id, kind, details=None):
        conn.execute(
            "INSERT INTO events(job_id,kind,details_json,created_at) VALUES(?,?,?,?)",
            (job_id, kind, json.dumps(details or {}, sort_keys=True), utc_now()),
        )

    def enqueue(self, kind, key, payload, *, max_attempts=3, connection=None):
        if kind not in self.TYPES or not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise EngineError("INVALID_JOB")
        if not 1 <= max_attempts <= 10:
            raise EngineError("INVALID_JOB")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode()) > 16384:
            raise EngineError("PAYLOAD_TOO_LARGE")
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.db.transaction() if connection is None else nullcontext(connection) as conn:
            existing = conn.execute(
                "SELECT * FROM jobs WHERE type=? AND idempotency_key=?", (kind, key)
            ).fetchone()
            if existing:
                if existing["payload_sha256"] != digest:
                    raise EngineError("IDEMPOTENCY_CONFLICT", status=409)
                return dict(existing)
            job_id, now = str(uuid4()), utc_now()
            conn.execute(
                """INSERT INTO jobs(id,type,status,idempotency_key,payload_json,payload_sha256,
                max_attempts,created_at,updated_at) VALUES(?,?,'queued',?,?,?,?,?,?)""",
                (job_id, kind, key, encoded, digest, max_attempts, now, now),
            )
            self.event(conn, job_id, "queued")
        return (
            dict(connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
            if connection is not None
            else self.get(job_id)
        )

    def find_key(self, kind, key):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE type=? AND idempotency_key=?", (kind, key)
            ).fetchone()
            return dict(row) if row else None

    def get(self, job_id):
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise EngineError("NOT_FOUND", status=404)
            return dict(row)

    def list(self, limit=100):
        with self.db.connection() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            ]

    def claim(self, job_id, *, now=None, lease_seconds=120):
        now = time.time() if now is None else now
        token = secrets.token_hex(16)
        with self.db.transaction() as conn:
            result = conn.execute(
                """UPDATE jobs SET status='running',attempt_count=attempt_count+1,
                lease_token=?,lease_until=?,heartbeat_at=?,updated_at=?,error_code=NULL
                WHERE id=? AND status IN ('queued','retry_wait') AND attempt_count<max_attempts""",
                (token, now + lease_seconds, now, utc_now(), job_id),
            )
            if result.rowcount != 1:
                return None
            row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
            conn.execute(
                "INSERT INTO job_attempts(job_id,attempt,lease_token,started_at) VALUES(?,?,?,?)",
                (job_id, row["attempt_count"], token, utc_now()),
            )
            self.event(conn, job_id, "claimed", {"attempt": row["attempt_count"]})
            return row

    @staticmethod
    def require_lease(conn, job_id, token, now=None):
        now = time.time() if now is None else now
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if (
            not row
            or row["status"] != "running"
            or row["lease_token"] != token
            or row["lease_until"] is None
            or row["lease_until"] <= now
        ):
            raise EngineError("LEASE_LOST", status=409)
        return row

    def heartbeat(self, job_id, token, *, seconds=120):
        with self.db.transaction() as conn:
            self.require_lease(conn, job_id, token)
            now = time.time()
            conn.execute(
                "UPDATE jobs SET heartbeat_at=?,lease_until=?,updated_at=? WHERE id=?",
                (now, now + seconds, utc_now(), job_id),
            )

    def complete(self, job_id, token, result_ref, *, now=None, connection=None):
        if not isinstance(result_ref, str) or not result_ref:
            raise EngineError("INVALID_RESULT")

        def apply(conn):
            self.require_lease(conn, job_id, token, now)
            stamp = utc_now()
            conn.execute(
                """UPDATE jobs SET status='completed',result_ref=?,lease_until=NULL,
                lease_token=NULL,updated_at=? WHERE id=?""",
                (result_ref, stamp, job_id),
            )
            conn.execute(
                "UPDATE job_attempts SET finished_at=?,outcome='completed' WHERE job_id=? AND lease_token=?",
                (stamp, job_id, token),
            )
            self.event(conn, job_id, "completed")

        if connection is not None:
            apply(connection)
        else:
            with self.db.transaction() as conn:
                apply(conn)

    def fail(self, job_id, token, code):
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None or row["status"] != "running" or row["lease_token"] != token:
                return
            conn.execute(
                "UPDATE jobs SET status='failed',error_code=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                (code, utc_now(), job_id),
            )
            conn.execute(
                "UPDATE job_attempts SET finished_at=?,outcome=? WHERE job_id=? AND lease_token=?",
                (utc_now(), code, job_id, token),
            )
            self.event(conn, job_id, "failed", {"code": code})

    def cancel(self, job_id):
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise EngineError("NOT_FOUND", status=404)
            if row["status"] in {"queued", "running", "retry_wait", "cancelling"}:
                conn.execute(
                    "UPDATE jobs SET status='cancelled',lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                    (utc_now(), job_id),
                )
                conn.execute(
                    "UPDATE job_attempts SET finished_at=?,outcome='cancelled' WHERE job_id=? AND finished_at IS NULL",
                    (utc_now(), job_id),
                )
                self.event(conn, job_id, "cancelled")
        return self.get(job_id)

    def recover_expired(self, *, now=None):
        now = time.time() if now is None else now
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status='running' AND lease_until<=?", (now,)
            ).fetchall()
            for row in rows:
                status = "retry_wait" if row["attempt_count"] < row["max_attempts"] else "failed"
                conn.execute(
                    "UPDATE jobs SET status=?,error_code='LEASE_EXPIRED',lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                    (status, utc_now(), row["id"]),
                )
                conn.execute(
                    "UPDATE job_attempts SET finished_at=?,outcome='lease_expired' WHERE job_id=? AND lease_token=?",
                    (utc_now(), row["id"], row["lease_token"]),
                )
                self.event(conn, row["id"], "lease_expired")
            return len(rows)

    def recover_owned_workspace(self, workspace_lock):
        # Only the process holding the exclusive workspace lock may fence a
        # predecessor immediately; wall-clock lease recovery alone cannot do so.
        import os

        if workspace_lock.stream.closed or workspace_lock.owner_pid != os.getpid():
            raise EngineError("WORKSPACE_LOCK_REQUIRED")
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status IN ('running','queued','cancelling')"
            ).fetchall()
            for row in rows:
                state = "retry_wait" if row["attempt_count"] < row["max_attempts"] else "failed"
                conn.execute(
                    "UPDATE jobs SET status=?,lease_until=NULL,lease_token=NULL,error_code='ENGINE_RESTARTED',updated_at=? WHERE id=?",
                    (state, utc_now(), row["id"]),
                )
                conn.execute(
                    "UPDATE job_attempts SET finished_at=?,outcome='engine_restarted' WHERE job_id=? AND lease_token=?",
                    (utc_now(), row["id"], row["lease_token"]),
                )
                self.event(conn, row["id"], "engine_restarted")
            conn.execute(
                "UPDATE answer_runs SET status='failed',error_code='ENGINE_RESTARTED' WHERE status IN ('running','queued') AND job_id IN (SELECT id FROM jobs WHERE status IN ('failed','retry_wait','cancelled'))"
            )
            conn.execute(
                "UPDATE research_items SET status='failed',error_code='ENGINE_RESTARTED' WHERE status='running'"
            )
            conn.execute("UPDATE research_plans SET status='partial' WHERE status='running'")
            conn.execute(
                "UPDATE parse_attempts SET status='failed',error_code='ENGINE_RESTARTED',finished_at=? WHERE status='running'",
                (utc_now(),),
            )
            conn.execute(
                "UPDATE parse_runs SET status='failed',error_code='ENGINE_RESTARTED',finished_at=? WHERE status='running'",
                (utc_now(),),
            )
        return len(rows)

    def retry(self, job_id):
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise EngineError("NOT_FOUND", status=404)
            if row["status"] not in {"failed", "cancelled", "retry_wait"}:
                raise EngineError("JOB_NOT_RETRYABLE", status=409)
            if row["attempt_count"] >= row["max_attempts"]:
                raise EngineError("ATTEMPT_LIMIT", status=409)
            conn.execute(
                "UPDATE jobs SET status='queued',error_code=NULL,result_ref=NULL,updated_at=? WHERE id=?",
                (utc_now(), job_id),
            )
            self.event(conn, job_id, "manual_retry")
        return self.get(job_id)
