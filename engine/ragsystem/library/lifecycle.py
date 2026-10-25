"""Reversible manual lifecycle flags, visibility fencing, immutable audit trail."""

import json
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.storage.database import utc_now


class Lifecycle:
    def __init__(self, db):
        self.db = db

    def records(self):
        with self.db.connection() as conn:
            values = []
            for row in conn.execute(
                "SELECT l.*,d.title FROM document_lifecycle l JOIN documents d ON d.id=l.document_id ORDER BY l.updated_at DESC,l.document_id"
            ):
                value = dict(row)
                value.pop("visibility_snapshot_json")
                value["origin"] = "manual_unverified"
                value["versions"] = [
                    dict(version)
                    for version in conn.execute(
                        "SELECT id AS doc_version_id,file_sha256,visibility FROM document_versions WHERE document_id=? ORDER BY id",
                        (row["document_id"],),
                    )
                ]
                value["history"] = [
                    dict(event)
                    for event in conn.execute(
                        "SELECT revision,before_json,after_json,actor,created_at FROM lifecycle_revisions WHERE document_id=? ORDER BY revision",
                        (row["document_id"],),
                    )
                ]
                values.append(value)
            return values

    def update(self, document_id, expected_revision, state, note):
        if (
            state not in {"active", "archived", "retracted"}
            or type(expected_revision) is not int
            or expected_revision < 0
            or not isinstance(note, str)
            or len(note) > 4000
            or not note.strip()
        ):
            raise EngineError("INVALID_LIFECYCLE")
        with self.db.transaction() as conn:
            versions = [
                dict(row)
                for row in conn.execute(
                    "SELECT id,visibility FROM document_versions WHERE document_id=? ORDER BY id",
                    (document_id,),
                )
            ]
            if not versions:
                raise EngineError("NOT_FOUND", status=404)
            row = conn.execute(
                "SELECT * FROM document_lifecycle WHERE document_id=?", (document_id,)
            ).fetchone()
            before = dict(row) if row else {"state": "active", "revision": 0, "note": ""}
            if before["revision"] != expected_revision:
                raise EngineError("LIFECYCLE_CONFLICT", status=409)
            # Only restore the exact visibility captured before this inactive period.
            snapshot = (
                json.loads(row["visibility_snapshot_json"])
                if row and before["state"] != "active"
                else versions
            )
            if state == "active":
                if {v["id"] for v in snapshot} != {v["id"] for v in versions}:
                    raise EngineError("LIFECYCLE_CONFLICT", status=409)
                conn.executemany(
                    "UPDATE document_versions SET visibility=? WHERE id=? AND document_id=?",
                    [(version["visibility"], version["id"], document_id) for version in snapshot],
                )
            else:
                conn.execute(
                    "UPDATE document_versions SET visibility='hidden' WHERE document_id=?",
                    (document_id,),
                )
            revision, stamp = expected_revision + 1, utc_now()
            after = {"state": state, "revision": revision, "note": note.strip()}
            conn.execute(
                "INSERT INTO document_lifecycle VALUES(?,?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET state=excluded.state,revision=excluded.revision,note=excluded.note,visibility_snapshot_json=excluded.visibility_snapshot_json,updated_at=excluded.updated_at",
                (document_id, state, revision, note.strip(), json.dumps(snapshot), stamp),
            )
            before.pop("visibility_snapshot_json", None)
            conn.execute(
                "INSERT INTO lifecycle_revisions VALUES(?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    document_id,
                    revision,
                    json.dumps(before),
                    json.dumps(after),
                    "local_user",
                    stamp,
                ),
            )
        return next(value for value in self.records() if value["document_id"] == document_id)

    @staticmethod
    def source_state(conn, version_id):
        row = conn.execute(
            "SELECT v.visibility,COALESCE(l.state,'active') AS state,COALESCE(l.note,'') AS note FROM document_versions v LEFT JOIN document_lifecycle l ON l.document_id=v.document_id WHERE v.id=?",
            (version_id,),
        ).fetchone()
        if not row:
            return {"state": "unavailable", "note": ""}
        return {
            "state": row["state"]
            if row["visibility"] == "visible" or row["state"] != "active"
            else "unavailable",
            "note": row["note"],
        }
