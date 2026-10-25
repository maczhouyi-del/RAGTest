import json
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.library.repository import Library
from ragsystem.storage.database import utc_now


class Identity:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def snapshot(conn, source, target):
        versions = [
            dict(row)
            for row in conn.execute(
                "SELECT id,document_id FROM document_versions WHERE document_id IN (?,?) ORDER BY id",
                (source, target),
            )
        ]
        memberships = [
            dict(row)
            for row in conn.execute(
                "SELECT project_id,document_id,linked FROM project_documents WHERE document_id IN (?,?) ORDER BY project_id,document_id",
                (source, target),
            )
        ]
        return {"versions": versions, "memberships": memberships}

    def merge(self, source, target, expected_versions):
        if source == target:
            raise EngineError("IDENTITY_CONFLICT", status=409)
        with self.db.transaction() as conn:
            Library.require_document(conn, source)
            Library.require_document(conn, target)
            before = self.snapshot(conn, source, target)
            if sorted(expected_versions) != sorted(row["id"] for row in before["versions"]):
                raise EngineError("IDENTITY_CONFLICT", status=409)
            for membership in before["memberships"]:
                if membership["document_id"] == source and membership["linked"]:
                    conn.execute(
                        "INSERT INTO project_documents VALUES(?,?,1,?) ON CONFLICT(project_id,document_id) DO UPDATE SET linked=1,updated_at=excluded.updated_at",
                        (membership["project_id"], target, utc_now()),
                    )
            conn.execute(
                "UPDATE document_versions SET document_id=? WHERE document_id=?", (target, source)
            )
            identifier = str(uuid4())
            after = self.snapshot(conn, source, target)
            conn.execute(
                "INSERT INTO document_merges VALUES(?,?,?,?,?,'active',?,NULL)",
                (identifier, source, target, json.dumps(before), json.dumps(after), utc_now()),
            )
        return {"id": identifier, "source_id": source, "target_id": target, "status": "active"}

    def undo(self, identifier):
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM document_merges WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise EngineError("NOT_FOUND", status=404)
            if row["status"] != "active" or self.snapshot(
                conn, row["source_id"], row["target_id"]
            ) != json.loads(row["after_json"]):
                raise EngineError("IDENTITY_CONFLICT", status=409)
            if conn.execute(
                "SELECT 1 FROM document_lifecycle WHERE document_id IN (?,?) AND state!='active'",
                (row["source_id"], row["target_id"]),
            ).fetchone():
                raise EngineError("IDENTITY_CONFLICT", status=409)
            before = json.loads(row["before_json"])
            for version in before["versions"]:
                conn.execute(
                    "UPDATE document_versions SET document_id=? WHERE id=?",
                    (version["document_id"], version["id"]),
                )
            original = {
                (item["project_id"], item["document_id"]): item["linked"]
                for item in before["memberships"]
            }
            for item in json.loads(row["after_json"])["memberships"]:
                conn.execute(
                    "UPDATE project_documents SET linked=?,updated_at=? WHERE project_id=? AND document_id=?",
                    (
                        original.get((item["project_id"], item["document_id"]), 0),
                        utc_now(),
                        item["project_id"],
                        item["document_id"],
                    ),
                )
            conn.execute(
                "UPDATE document_merges SET status='undone',undone_at=? WHERE id=?",
                (utc_now(), identifier),
            )
        return {"id": identifier, "status": "undone"}

    def records(self):
        with self.db.connection() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT m.id,m.source_id,m.target_id,s.title AS source_title,t.title AS target_title,m.status,m.created_at,m.undone_at FROM document_merges m JOIN documents s ON s.id=m.source_id JOIN documents t ON t.id=m.target_id ORDER BY m.created_at DESC LIMIT 100"
                )
            ]
