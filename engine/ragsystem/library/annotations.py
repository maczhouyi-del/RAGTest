import json
import os
import subprocess
import sys
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.library.repository import Library
from ragsystem.retrieval.source_search import Sources
from ragsystem.storage.database import utc_now


class Annotations:
    def __init__(self, db, root):
        self.db, self.root = db, root

    def list(self, version):
        Library(self.db).file_record(version, self.root)
        with self.db.connection() as conn:
            values = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM annotations WHERE doc_version_id=? ORDER BY page_number,created_at",
                    (version,),
                )
            ]
            for value in values:
                value["history"] = [
                    dict(row)
                    for row in conn.execute(
                        "SELECT revision,note,created_at FROM annotation_revisions WHERE annotation_id=? ORDER BY revision",
                        (value["id"],),
                    )
                ]
            return values

    def save(self, version, body):
        record = Library(self.db).file_record(version, self.root)
        path = self.root / "papers" / (record["file_sha256"] + ".pdf")
        command = (
            [sys.executable, "--parse-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "ragsystem.parsing.worker"]
        )
        try:
            result = subprocess.run(
                command,
                input=json.dumps(
                    {"pdf_path": str(path), "parent_pid": os.getpid(), "operation": "page_count"}
                ),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode or len(result.stdout) > 1024:
                raise ValueError("failed")
            count = json.loads(result.stdout)["page_count"]
        except (subprocess.TimeoutExpired, ValueError, KeyError) as exc:
            raise EngineError("PDF_EXTRACTION_FAILED") from exc
        if not 1 <= body.page_number <= count:
            raise EngineError("SOURCE_PAGE_INVALID")
        if body.source_anchor_id:
            anchor = Sources(self.db, self.root).anchor(body.source_anchor_id)
            if anchor["doc_version_id"] != version or anchor["page_number"] != body.page_number:
                raise EngineError("SOURCE_ALIGNMENT_INVALID")
        with self.db.transaction() as conn:
            stamp = utc_now()
            if body.annotation_id:
                row = conn.execute(
                    "SELECT * FROM annotations WHERE id=? AND doc_version_id=?",
                    (body.annotation_id, version),
                ).fetchone()
                if (
                    row is None
                    or row["revision"] != body.expected_revision
                    or row["page_number"] != body.page_number
                ):
                    raise EngineError("ANNOTATION_CONFLICT", status=409)
                annotation_id, revision = row["id"], row["revision"] + 1
                conn.execute(
                    "UPDATE annotations SET note=?,revision=?,updated_at=? WHERE id=?",
                    (body.note, revision, stamp, annotation_id),
                )
            else:
                if body.expected_revision != 0:
                    raise EngineError("ANNOTATION_CONFLICT", status=409)
                annotation_id, revision = str(uuid4()), 1
                conn.execute(
                    "INSERT INTO annotations VALUES(?,?,?,?,?,?,?,?)",
                    (
                        annotation_id,
                        version,
                        body.source_anchor_id,
                        body.page_number,
                        body.note,
                        revision,
                        stamp,
                        stamp,
                    ),
                )
            conn.execute(
                "INSERT INTO annotation_revisions VALUES(?,?,?,?)",
                (annotation_id, revision, body.note, stamp),
            )
        return {"id": annotation_id, "revision": revision}
