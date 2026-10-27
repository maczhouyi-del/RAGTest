"""Owned incomplete outputs are quarantined, never recursively deleted.

Uses existing app_settings, bound to the original workspace so restored journals
can never rename outputs owned by their source workspace.
"""

import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.ipc.directories import directory_identity
from ragsystem.storage.database import utc_now

MARKER = ".ragsystem-operation.json"
PREFIX = "backup-operation:"


def write_marker(path, value):
    temporary = path / (".operation-state-" + str(uuid4()) + ".json")
    with temporary.open("x") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path / MARKER)


class BackupOperations:
    def __init__(self, db, root):
        self.db, self.root = db, Path(root).absolute()

    def save(self, value):
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO app_settings VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                (PREFIX + value["id"], json.dumps(value), utc_now()),
            )

    def begin(self, kind, parent, job_id=None, identifier=None):
        identifier = identifier or str(uuid4())
        parent = Path(parent)
        name = ("ragsystem-restored-" if kind == "restored" else "ragsystem-backup-") + identifier
        value = {
            "id": identifier,
            "kind": kind,
            "owner_root": str(self.root),
            "parent": str(parent),
            "parent_identity": list(directory_identity(parent)),
            "target": str(parent / name),
            "original_name": name,
            "job_id": job_id,
            "state": "planned",
            "target_identity": None,
        }
        self.save(value)
        return value

    def prepare(self, value):
        target = Path(value["target"])
        if list(directory_identity(target.parent)) != value["parent_identity"]:
            raise EngineError("DIRECTORY_CHANGED")
        target.mkdir(exist_ok=False)
        value["target_identity"] = list(directory_identity(target))
        write_marker(
            target, {"id": value["id"], "owner_root": value["owner_root"], "state": "incomplete"}
        )
        value["state"] = "active"
        self.save(value)
        return target

    def verify(self, value):
        target = Path(value["target"])
        if value["owner_root"] != str(self.root) or target == self.root:
            raise EngineError("BACKUP_OWNERSHIP_UNVERIFIED")
        if (
            target.name != value["original_name"]
            or list(directory_identity(target.parent)) != value["parent_identity"]
            or list(directory_identity(target)) != value["target_identity"]
        ):
            raise EngineError("BACKUP_OWNERSHIP_UNVERIFIED")
        marker = target / MARKER
        if (target / "data/.engine.lock").exists():
            # A workspace which has ever been activated requires manual review.
            raise EngineError("BACKUP_OWNERSHIP_UNVERIFIED")
        if marker.is_symlink() or marker.stat().st_size > 4096:
            raise EngineError("BACKUP_OWNERSHIP_UNVERIFIED")
        saved = json.loads(marker.read_text())
        if saved.get("id") != value["id"] or saved.get("owner_root") != str(self.root):
            raise EngineError("BACKUP_OWNERSHIP_UNVERIFIED")
        return target

    def complete(self, value):
        target = self.verify(value)
        write_marker(target, {"id": value["id"], "owner_root": str(self.root), "state": "complete"})
        value["state"] = "complete"
        self.save(value)

    def quarantine(self, value, code):
        if value["state"] == "complete":
            return True
        try:
            if value["target_identity"] is None and not Path(value["target"]).exists():
                value.update(state="no_output", error_code=code)
                self.save(value)
                return True
            target = self.verify(value)
            quarantine = target.with_name(target.name + ".incomplete-" + str(uuid4()))
            value["quarantine_target"] = str(quarantine)
            value["state"] = "quarantining"
            self.save(value)
            target.rename(quarantine)
            value.update(target=str(quarantine), state="quarantined", error_code=code)
        except (OSError, ValueError, EngineError, sqlite3.Error):
            # An unverifiable or unavailable path is recorded and left untouched.
            value.update(
                state="manual_review", error_code="BACKUP_OWNERSHIP_UNVERIFIED", cause_code=code
            )
        try:
            self.save(value)
        except (OSError, sqlite3.Error):
            # The prior durable planned/active record is retained for next startup.
            return False
        return value["state"] == "quarantined"

    def rows(self):
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT value_json FROM app_settings WHERE key LIKE ?", (PREFIX + "%",)
            ).fetchall()
        return [
            value
            for row in rows
            if (value := json.loads(row[0])).get("owner_root") == str(self.root)
        ]

    def reconcile(self):
        for value in self.rows():
            if value["state"] == "quarantining":
                moved = Path(value.get("quarantine_target", ""))
                try:
                    if (
                        list(directory_identity(moved)) == value["target_identity"]
                        and json.loads((moved / MARKER).read_text())["id"] == value["id"]
                    ):
                        value.update(
                            target=str(moved), state="quarantined", error_code="BACKUP_INTERRUPTED"
                        )
                        self.save(value)
                        continue
                except (EngineError, OSError, ValueError, KeyError):
                    pass  # Original registered target is checked below; nothing is removed.
            if value["state"] not in {"planned", "active", "quarantining", "complete"}:
                continue
            with self.db.connection() as conn:
                job = conn.execute(
                    "SELECT status FROM jobs WHERE id=?", (value.get("job_id"),)
                ).fetchone()
                published = conn.execute(
                    "SELECT 1 FROM backup_records WHERE id=?", (value["id"],)
                ).fetchone()
            if published or (value["state"] == "complete" and value.get("job_id") is None):
                continue
            if job and job["status"] == "running":
                continue
            value["state"] = "active"
            self.quarantine(value, "BACKUP_INTERRUPTED")

    def issues(self):
        return [
            {key: value.get(key) for key in ("id", "kind", "state", "error_code")}
            for value in self.rows()
            if value["state"] in {"quarantined", "manual_review"}
        ]
