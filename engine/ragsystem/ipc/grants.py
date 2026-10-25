import hashlib
import os
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import BinaryIO

from ragsystem.domain.errors import EngineError

MAX_PDF_BYTES = 64 * 1024 * 1024


@dataclass
class FileGrant:
    id: str
    source: BinaryIO
    display_name: str
    sha256: str
    size: int
    expires: float


def digest_stream(source: BinaryIO, limit=MAX_PDF_BYTES):
    source.seek(0)
    digest = hashlib.sha256()
    total = 0
    while data := source.read(1024 * 1024):
        total += len(data)
        if total > limit:
            raise EngineError("PDF_TOO_LARGE", status=413)
        digest.update(data)
    source.seek(0)
    return digest.hexdigest(), total


class Grants:
    def __init__(self):
        self._grants: dict[str, FileGrant] = {}
        self._lock = Lock()

    def issue(self, path: Path) -> FileGrant:
        path = Path(path)
        if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
            raise EngineError("FILE_NOT_ALLOWED", status=403)
        # Refuse symlinks/reparse points before opening. The held descriptor, not
        # the path string, is used for the import; its hash is checked again.
        for part in [path, *path.parents]:
            if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
                raise EngineError("FILE_NOT_ALLOWED", status=403)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
            source = os.fdopen(fd, "rb")
        except OSError as exc:
            raise EngineError("FILE_NOT_ALLOWED", status=403) from exc
        try:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise EngineError("FILE_NOT_ALLOWED", status=403)
            if info.st_size > MAX_PDF_BYTES:
                raise EngineError("PDF_TOO_LARGE", status=413)
            if not source.read(8).startswith(b"%PDF-"):
                raise EngineError("NOT_PDF")
            digest, size = digest_stream(source)
            grant = FileGrant(
                secrets.token_hex(24), source, path.name, digest, size, time.monotonic() + 300
            )
            with self._lock:
                for key, old in list(self._grants.items()):
                    if old.expires < time.monotonic():
                        old.source.close()
                        del self._grants[key]
                if len(self._grants) >= 32:
                    raise EngineError("GRANT_LIMIT", status=429)
                self._grants[grant.id] = grant
            return grant
        except BaseException:
            source.close()
            raise

    def take(self, grant_id: str) -> FileGrant:
        with self._lock:
            grant = self._grants.pop(grant_id, None)
        if not grant:
            raise EngineError("GRANT_INVALID", status=403)
        if grant.expires < time.monotonic():
            grant.source.close()
            raise EngineError("GRANT_EXPIRED", status=403)
        return grant

    def close(self):
        with self._lock:
            for grant in self._grants.values():
                grant.source.close()
            self._grants.clear()
