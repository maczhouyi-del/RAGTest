"""Generation-local file manifests; derived indexes cannot silently change."""

import hashlib
import re
from pathlib import Path

from ragsystem.domain.errors import EngineError


def checked_path(root, relative):
    if not re.fullmatch(r"vectors/[0-9a-f-]{36}/(?:index\.db|lance)", relative):
        raise EngineError("INDEX_INVALID")
    path = Path(root) / relative
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise EngineError("INDEX_INVALID")
    return path


def files(path):
    if not path.exists():
        raise EngineError("INDEX_INVALID")
    result = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    if not result or len(result) > 100000 or any(p.is_symlink() for p in result):
        raise EngineError("INDEX_INVALID")
    return result


def stamp(path):
    return tuple(
        (str(p.relative_to(path.parent)), p.stat().st_size, p.stat().st_mtime_ns)
        for p in files(path)
    )


def manifest(path):
    result = {}
    for p in files(path):
        with p.open("rb") as stream:
            result[str(p.relative_to(path.parent))] = hashlib.file_digest(
                stream, "sha256"
            ).hexdigest()
    return result
