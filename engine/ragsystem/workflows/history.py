"""Bounded history pages and lazy detail reads; SQLite remains authoritative."""

import base64
import json
import re
from datetime import datetime
from uuid import UUID

from ragsystem.domain.errors import EngineError
from ragsystem.library.lifecycle import Lifecycle
from ragsystem.storage.database import utc_now


def encode_cursor(row):
    return (
        base64.urlsafe_b64encode(
            json.dumps([row["created_at"], row["id"]], separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )


def decode_cursor(value):
    try:
        if len(value) > 512 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError()
        stamp, identifier = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        if (
            not isinstance(stamp, str)
            or len(stamp) > 64
            or datetime.fromisoformat(stamp).tzinfo is None
        ):
            raise ValueError()
        UUID(identifier)
        return stamp, identifier
    except (ValueError, TypeError, UnicodeError) as exc:
        raise EngineError("INVALID_CURSOR") from exc


def _history_page(rows, total, limit):
    # Queries fetch one lookahead row. Keep the cursor on the last returned
    # descending row, even when the chat later displays that page in reverse.
    return {
        "items": rows[:limit],
        "total": total,
        "next_cursor": encode_cursor(rows[limit - 1]) if len(rows) > limit else None,
    }


class History:
    def __init__(self, workbench):
        self.work, self.db = workbench, workbench.db

    def conversations(self, project_id=None, cursor=None, limit=30, archived=False):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise EngineError("INVALID_REQUEST")
        archive_filter = "c.archived_at IS NOT NULL" if archived else "c.archived_at IS NULL"
        suffix, args = "", [project_id]
        if cursor:
            stamp, identifier = decode_cursor(cursor)
            suffix = " AND (c.updated_at<? OR (c.updated_at=? AND c.id<?))"
            args += [stamp, stamp, identifier]
        with self.db.connection() as conn:
            conn.execute("BEGIN")
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT c.id,c.title,c.title AS question,c.updated_at AS created_at,c.updated_at,c.archived_at,"
                    "(SELECT count(*) FROM answer_runs a WHERE a.conversation_id=c.id) AS turn_count "
                    "FROM conversations c WHERE c.project_id IS ? AND " + archive_filter
                    + suffix
                    + " ORDER BY c.updated_at DESC,c.id DESC LIMIT ?",
                    [*args, limit + 1],
                )
            ]
            total = conn.execute(
                "SELECT count(*) FROM conversations c WHERE c.project_id IS ? AND " + archive_filter, (project_id,)
            ).fetchone()[0]
        return _history_page(rows, total, limit)

    def manage_conversation(self, identifier, action, project_id=None, title=None):
        if action not in {"rename", "archive", "restore", "delete"}:
            raise EngineError("INVALID_REQUEST")
        if action == "rename" and (not isinstance(title, str) or not title.strip() or len(title.strip()) > 160):
            raise EngineError("INVALID_CONVERSATION_TITLE")
        # The same writer lock fences new turns, job claims/retries and deletion.
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id=? AND project_id IS ?", (identifier, project_id)).fetchone()
            if row is None:
                raise EngineError("NOT_FOUND", status=404)
            if action != "delete":
                if action == "rename":
                    conn.execute("UPDATE conversations SET title=?,renamed_at=? WHERE id=?", (title.strip(), utc_now(), identifier))
                else:
                    conn.execute("UPDATE conversations SET archived_at=? WHERE id=?", (utc_now() if action == "archive" else None, identifier))
                return dict(conn.execute("SELECT * FROM conversations WHERE id=?", (identifier,)).fetchone())
            runs = [dict(r) for r in conn.execute("SELECT a.id,a.job_id,a.scope_id,j.status,j.lease_token FROM answer_runs a JOIN jobs j ON j.id=a.job_id WHERE a.conversation_id=?", (identifier,))]
            if any(r['status'] not in {'completed', 'failed', 'cancelled'} or r['lease_token'] for r in runs):
                raise EngineError("CONVERSATION_BUSY", status=409)
            # Evidence may be referenced by research revisions; refuse instead of
            # cascading into research or any unrelated owner.
            if conn.execute("SELECT 1 FROM observation_revisions o JOIN evidence_records e ON e.id=o.evidence_id JOIN answer_runs a ON a.id=e.owner_id WHERE a.conversation_id=? LIMIT 1", (identifier,)).fetchone():
                raise EngineError("CONVERSATION_REFERENCED", status=409)
            for run in runs:
                run_id = run['id']
                conn.execute("DELETE FROM human_reviews WHERE target_id=? OR target_id IN (SELECT id FROM claim_records WHERE run_id=?) OR target_id IN (SELECT id FROM evidence_records WHERE owner_id=?)", (run_id, run_id, run_id))
                conn.execute("DELETE FROM claim_records WHERE run_id=?", (run_id,))
                conn.execute("DELETE FROM evidence_records WHERE owner_id=?", (run_id,))
                conn.execute("DELETE FROM answer_runs WHERE id=?", (run_id,))
                # Normally one job per turn; never remove a shared task/scope.
                if not conn.execute("SELECT 1 FROM answer_runs WHERE job_id=?", (run['job_id'],)).fetchone():
                    conn.execute("DELETE FROM events WHERE job_id=?", (run['job_id'],))
                    conn.execute("DELETE FROM job_attempts WHERE job_id=?", (run['job_id'],))
                    conn.execute("DELETE FROM jobs WHERE id=?", (run['job_id'],))
                conn.execute("DELETE FROM scope_snapshots WHERE id=? AND NOT EXISTS(SELECT 1 FROM answer_runs WHERE scope_id=?) AND NOT EXISTS(SELECT 1 FROM research_plans WHERE scope_id=?)", (run['scope_id'], run['scope_id'], run['scope_id']))
            conn.execute("DELETE FROM conversations WHERE id=?", (identifier,))
            return {"id": identifier, "deleted": True, "deleted_turns": len(runs)}

    def turns(self, identifier, project_id=None, cursor=None, limit=30):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise EngineError("INVALID_REQUEST")
        suffix, args = "", [identifier]
        if cursor:
            stamp, run_id = decode_cursor(cursor)
            suffix = " AND (created_at<? OR (created_at=? AND id<?))"
            args += [stamp, stamp, run_id]
        with self.db.connection() as conn:
            conn.execute("BEGIN")
            conversation = conn.execute(
                "SELECT * FROM conversations WHERE id=? AND project_id IS ?",
                (identifier, project_id),
            ).fetchone()
            if conversation is None:
                raise EngineError("NOT_FOUND", status=404)
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT id,created_at FROM answer_runs WHERE conversation_id=?"
                    + suffix
                    + " ORDER BY created_at DESC,id DESC LIMIT ?",
                    [*args, limit + 1],
                )
            ]
            total = conn.execute(
                "SELECT count(*) FROM answer_runs WHERE conversation_id=?", (identifier,)
            ).fetchone()[0]
        page = _history_page(rows, total, limit)
        page["conversation"] = dict(conversation)
        page["items"] = [self.answer(r["id"], project_id) for r in reversed(page["items"])]
        return page

    def index(self, kind, project_id=None, cursor=None, limit=30):
        if kind in {"conversations", "archived_conversations"}:
            return self.conversations(project_id, cursor, limit, kind == "archived_conversations")
        if kind not in {"answers", "research"} or type(limit) is not int or not 1 <= limit <= 50:
            raise EngineError("INVALID_REQUEST")
        table = "answer_runs" if kind == "answers" else "research_plans"
        columns = "r.conversation_id,r.error_code," if kind == "answers" else ""
        where, parameters = "", [project_id]
        if cursor:
            stamp, identifier = decode_cursor(cursor)
            where = " AND (r.created_at<? OR (r.created_at=? AND r.id<?))"
            parameters.extend([stamp, stamp, identifier])
        with self.db.connection() as conn:
            conn.execute("BEGIN")
            rows = [
                dict(row)
                for row in conn.execute(
                    f"SELECT r.id,r.question,r.mode,r.status,r.created_at,{columns}s.id AS scope_id "
                    f"FROM {table} r JOIN scope_snapshots s ON s.id=r.scope_id WHERE s.project_id IS ?{where} ORDER BY r.created_at DESC,r.id DESC LIMIT ?",
                    [*parameters, limit + 1],
                )
            ]
            total = conn.execute(
                f"SELECT COUNT(*) FROM {table} r JOIN scope_snapshots s ON s.id=r.scope_id WHERE s.project_id IS ?",
                (project_id,),
            ).fetchone()[0]
        return _history_page(rows, total, limit)

    def answer(self, identifier, project_id):
        values = self.work.answers(project_id, run_id=identifier)
        if not values:
            raise EngineError("NOT_FOUND", status=404)
        return values[0]

    def research(self, identifier, project_id, paper_offset=0, observation_offset=0, limit=20):
        if (
            type(paper_offset) is not int
            or paper_offset < 0
            or type(observation_offset) is not int
            or observation_offset < 0
            or not 1 <= limit <= 50
        ):
            raise EngineError("INVALID_REQUEST")
        with self.db.connection() as conn:
            conn.execute("BEGIN")
            row = conn.execute(
                "SELECT p.*,s.versions_json FROM research_plans p JOIN scope_snapshots s ON s.id=p.scope_id WHERE p.id=? AND s.project_id IS ?",
                (identifier, project_id),
            ).fetchone()
            if row is None:
                raise EngineError("NOT_FOUND", status=404)
            plan = dict(row)
            scope = json.loads(plan.pop("versions_json"))
            if paper_offset >= len(scope):
                raise EngineError("INVALID_PAGE")
            selected = scope[paper_offset]
            plan["scope"] = [selected]
            plan["scope_count"] = len(scope)
            plan["paper_list"] = [
                {"doc_version_id": doc["doc_version_id"], "title": doc["title"]} for doc in scope
            ]
            plan["fields"] = json.loads(plan.pop("fields_json"))
            plan["model_history"] = self.work.model_history(conn, identifier)
            plan["scope_warnings"], plan["source_warnings"] = [], []
            for document in scope:
                version = document["doc_version_id"]
                current = conn.execute(
                    "SELECT document_id FROM document_versions WHERE id=?", (version,)
                ).fetchone()
                if (
                    not document.get("document_id")
                    or not current
                    or current[0] != document["document_id"]
                ):
                    plan["scope_warnings"].append(
                        {"doc_version_id": version, "code": "SCOPE_IDENTITY_CHANGED"}
                    )
                state = Lifecycle.source_state(conn, version)
                if state["state"] != "active":
                    plan["source_warnings"].append({"doc_version_id": version, **state})
            counts = dict(
                conn.execute(
                    "SELECT status,COUNT(*) FROM research_items WHERE plan_id=? GROUP BY status",
                    (identifier,),
                ).fetchall()
            )
            plan["coverage"] = {
                state: counts.get(state, 0)
                for state in (
                    "pending",
                    "running",
                    "completed",
                    "partial",
                    "failed",
                    "cancelled",
                    "needs_parse",
                    "needs_ocr",
                )
            }
            item = dict(
                conn.execute(
                    "SELECT * FROM research_items WHERE plan_id=? AND doc_version_id=?",
                    (identifier, selected["doc_version_id"]),
                ).fetchone()
            )
            observations = json.loads(item.pop("observations_json"))
            item["observation_count"] = len(observations)
            item["field_counts"] = {
                field: sum(obs["field"] == field for obs in observations)
                for field in plan["fields"]
            }
            item["observations"] = observations[observation_offset : observation_offset + limit]
            item["observation_offset"] = observation_offset
            item["observation_next_offset"] = (
                observation_offset + limit
                if observation_offset + limit < len(observations)
                else None
            )
            plan["items"] = [item]
            plan["paper_offset"] = paper_offset
            plan["evidence"] = []
            for observation in item["observations"]:
                record = conn.execute(
                    "SELECT * FROM evidence_records WHERE id=? AND owner_id=?",
                    (observation["evidence_id"], identifier),
                ).fetchone()
                if record:
                    plan["evidence"].append(self.work.public_evidence(record))
            plan["reports"] = [
                dict(row)
                for row in conn.execute(
                    "SELECT id,revision,created_at FROM report_revisions WHERE plan_id=? ORDER BY revision DESC",
                    (identifier,),
                )
            ]
        return plan
