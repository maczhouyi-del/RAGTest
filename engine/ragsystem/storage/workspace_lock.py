"""One live sidecar per workspace; lock file is retained, never deleted."""

import os
import sys
from pathlib import Path

from ragsystem.domain.errors import EngineError


class WorkspaceLock:
    def __init__(self, root):
        directory = Path(root) / "data"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / ".engine.lock"
        if path.is_symlink():
            raise EngineError("WORKSPACE_LOCK_INVALID")
        self.stream = path.open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                if path.stat().st_size == 0:
                    self.stream.write(b"0")
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.owner_pid = os.getpid()
        except OSError as exc:
            self.stream.close()
            raise EngineError("WORKSPACE_IN_USE") from exc

    def close(self):
        if self.stream.closed:
            return
        if sys.platform == "win32":
            import msvcrt

            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.stream.close()
