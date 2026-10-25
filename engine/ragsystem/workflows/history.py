"""Bounded history pages and lazy detail reads; SQLite remains authoritative."""

import base64
import json
import re
from datetime import datetime
from uuid import UUID

from ragsystem.domain.errors import EngineError
from ragsystem.library.lifecycle import Lifecycle


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


class History:
    def __init__(self, workbench):
        self.work, self.db = workbench, workbench.db

    def index(self, kind, project_id=None, cursor=None, limit=30):
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
        return {
            "items": rows[:limit],
            "next_cursor": encode_cursor(rows[limit - 1]) if len(rows) > limit else None,
            "total": total,
        }

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
