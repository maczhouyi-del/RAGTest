import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from ragsystem.domain.errors import EngineError


def directory_identity(path):
    path = Path(path)
    if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
        raise EngineError("DIRECTORY_NOT_ALLOWED", status=403)
    for part in [path, *path.parents]:
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise EngineError("DIRECTORY_NOT_ALLOWED", status=403)
    try:
        info = path.stat()
        if not path.is_dir():
            raise OSError("not a directory")
        return info.st_dev, info.st_ino
    except OSError as exc:
        raise EngineError("DIRECTORY_NOT_ALLOWED", status=403) from exc


@dataclass
class DirectoryGrant:
    id: str
    path: Path
    purpose: str
    identity: tuple
    expires: float

    def check(self):
        if directory_identity(self.path) != self.identity:
            raise EngineError("DIRECTORY_CHANGED", status=409)


class Directories:
    def __init__(self):
        self.grants = {}
        self.lock = Lock()

    def issue(self, path, purpose):
        if purpose not in {
            "backup_parent",
            "snapshot",
            "restore_parent",
            "embedding",
            "generator",
            "ocr",
            "docling",
        }:
            raise EngineError("DIRECTORY_PURPOSE_INVALID")
        grant = DirectoryGrant(
            secrets.token_hex(24),
            Path(path),
            purpose,
            directory_identity(path),
            time.monotonic() + 300,
        )
        with self.lock:
            self.grants = {
                key: row for key, row in self.grants.items() if row.expires > time.monotonic()
            }
            if len(self.grants) >= 16:
                raise EngineError("GRANT_LIMIT", status=429)
            self.grants[grant.id] = grant
        return grant

    def take(self, identifier, purpose):
        with self.lock:
            grant = self.grants.pop(identifier, None)
        if grant is None or grant.purpose != purpose:
            raise EngineError("GRANT_INVALID", status=403)
        if grant.expires <= time.monotonic():
            raise EngineError("GRANT_EXPIRED", status=403)
        grant.check()
        return grant
