"""One broker-owned sidecar: bounded stdin handshake, ephemeral loopback port."""

import json
import socket
import sys
from pathlib import Path

import uvicorn

from ragsystem.domain.errors import EngineError
from ragsystem.ipc.server import create_app

PROTOCOL_VERSION = "0.1.0"


def main():
    # Never accept a token or arbitrary executable/network arguments via argv.
    try:
        if sys.argv[1:] == ["--parse-worker"]:
            from ragsystem.parsing.worker import main as worker_main

            return worker_main()
        if sys.argv[1:] == ["--generation-worker"]:
            from ragsystem.models.generator_worker import main as generation_main

            return generation_main()
        if len(sys.argv) != 1:
            raise EngineError("STARTUP_ARGUMENTS_FORBIDDEN")
        line = sys.stdin.buffer.readline(16385)
        if not line.endswith(b"\n") or len(line) > 16384:
            raise EngineError("STARTUP_TOO_LARGE")
        config = json.loads(line)
        if (
            set(config) != {"protocol_version", "token", "data_root"}
            or config["protocol_version"] != PROTOCOL_VERSION
        ):
            raise EngineError("PROTOCOL_MISMATCH")
        root = Path(config["data_root"])
        if not root.is_absolute():
            raise EngineError("INVALID_DATA_ROOT")
        from ragsystem.jobs.repository import Jobs
        from ragsystem.storage.database import Database
        from ragsystem.storage.workspace_lock import WorkspaceLock

        workspace_lock = WorkspaceLock(root)
        Jobs(Database(root / "data/research.db")).recover_owned_workspace(workspace_lock)
        app = create_app(config["token"], root)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                access_log=False,
                log_config=None,
                log_level="critical",
                limit_concurrency=8,
                timeout_keep_alive=2,
                timeout_graceful_shutdown=5,
                h11_max_incomplete_event_size=16384,
            )
        )

        # Rust verifies readiness with an authenticated /health after this line.
        # Pipe EOF is a controlled parent-death signal; no stdin text is executed.
        import threading

        def parent_watch():
            while sys.stdin.buffer.read(1):
                pass
            server.should_exit = True

        threading.Thread(target=parent_watch, daemon=True).start()
        print(json.dumps({"protocol_version": PROTOCOL_VERSION, "port": port}), flush=True)
        server.run(sockets=[listener])
        listener.close()
        workspace_lock.close()
    except (EngineError, ValueError, KeyError, TypeError, OSError) as exc:
        code = exc.code if isinstance(exc, EngineError) else "STARTUP_FAILED"
        print(json.dumps({"code": code}), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
