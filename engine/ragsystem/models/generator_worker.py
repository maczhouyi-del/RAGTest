"""A supervised local generation worker, using private bounded pipes, no server."""

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

from ragsystem.domain.errors import EngineError

MAX_MESSAGE = 256 * 1024


class IsolatedGenerator:
    def __init__(self, path, diagnostic_directory=None, cancel_check=None):
        self.diagnostic_directory = (
            Path(diagnostic_directory)
            if diagnostic_directory
            else Path(tempfile.gettempdir()) / "RAGSystem-model-logs"
        )
        self.diagnostic_directory.mkdir(parents=True, exist_ok=True)
        self.path, self.process, self.cancel_check = str(path), None, cancel_check
        self.lock = threading.Lock()
        self.fingerprint = None
        self.start()

    def start(self):
        command = (
            [sys.executable, "--generation-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "ragsystem.models.generator_worker"]
        )
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.process, self.messages = process, queue.Queue()
        self.diagnostic_path = self.diagnostic_directory / ("worker-" + str(uuid4()) + ".log")
        diagnostic_path = self.diagnostic_path

        def diagnostics():
            written, truncated = 0, False
            with diagnostic_path.open("xb") as stream:
                stream.write(b"Local generation worker stderr; capped at 1 MiB.\n")
                while chunk := process.stderr.read(4096):
                    keep = chunk[: max(0, 1024 * 1024 - written)]
                    stream.write(keep)
                    written += len(keep)
                    if len(keep) < len(chunk) and not truncated:
                        stream.write(b"\n[stderr truncated at explicit 1 MiB bound]\n")
                        truncated = True

        threading.Thread(target=diagnostics, daemon=True).start()
        messages = self.messages

        def read():
            try:
                while True:
                    line = process.stdout.readline(MAX_MESSAGE + 1)
                    messages.put(line)
                    if not line or len(line) > MAX_MESSAGE:
                        break
            except OSError:
                messages.put(b"")

        threading.Thread(target=read, daemon=True).start()
        try:
            self.send({"model_path": self.path, "parent_pid": os.getpid()})
            reply = self.receive(60)
            if reply.get("ok") is not True:
                raise EngineError(reply.get("code", "MODEL_LOAD_FAILED"))
            fingerprint = reply["fingerprint"] | {"isolation": "private-pipe-worker-v1"}
            if self.fingerprint is not None and fingerprint != self.fingerprint:
                raise EngineError("MODEL_FINGERPRINT_CHANGED")
            self.fingerprint = fingerprint
        except BaseException:
            self.close()
            raise

    def send(self, value):
        encoded = (json.dumps(value, ensure_ascii=False) + "\n").encode()
        if len(encoded) > 128 * 1024:
            raise EngineError("MODEL_CONTEXT_LIMIT")
        try:
            self.process.stdin.write(encoded)
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise EngineError("MODEL_WORKER_FAILED") from exc

    def receive(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.cancel_check:
                self.cancel_check()
            try:
                line = self.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if not line or len(line) > MAX_MESSAGE:
                raise EngineError("MODEL_WORKER_FAILED")
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("not object")
                return value
            except (ValueError, TypeError) as exc:
                raise EngineError("MODEL_WORKER_FAILED") from exc
        raise EngineError("MODEL_TIMEOUT")

    def generate(self, task, data):
        if task not in {"answer", "research", "support", "relevance"}:
            raise EngineError("MODEL_TASK_INVALID")
        with self.lock:
            try:
                if self.process is None or self.process.poll() is not None:
                    self.start()
                self.send({"task": task, "data": data})
                reply = self.receive(180)
                if reply.get("ok") is not True:
                    raise EngineError(reply.get("code", "MODEL_OUTPUT_INVALID"))
                return reply["result"]
            except BaseException:
                self.close()
                raise

    def close(self):
        process, self.process = self.process, None
        if process is None:
            return
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for stream in (process.stdin, process.stdout):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass

    def __del__(self):
        self.close()


def main():
    from ragsystem.models.local_generator import LocalGenerator
    from ragsystem.parsing.worker import watch_parent

    try:
        initial = json.loads(sys.stdin.buffer.readline(16384))
        if set(initial) != {"model_path", "parent_pid"}:
            raise EngineError("MODEL_INPUT_INVALID")
        watch_parent(initial["parent_pid"])
        generator = LocalGenerator(initial["model_path"])
        print(json.dumps({"ok": True, "fingerprint": generator.fingerprint}), flush=True)
        while line := sys.stdin.buffer.readline(128 * 1024 + 1):
            if len(line) > 128 * 1024 or not line.endswith(b"\n"):
                raise EngineError("MODEL_INPUT_INVALID")
            try:
                body = json.loads(line)
                if set(body) != {"task", "data"} or not isinstance(body["data"], dict):
                    raise EngineError("MODEL_INPUT_INVALID")
                result = generator.generate(body["task"], body["data"])
                response = {"ok": True, "result": result}
                if len(json.dumps(response).encode()) > MAX_MESSAGE - 1:
                    raise EngineError("MODEL_OUTPUT_INVALID")
            except Exception as exc:
                response = {
                    "ok": False,
                    "code": exc.code if isinstance(exc, EngineError) else "MODEL_WORKER_FAILED",
                }
            print(json.dumps(response, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code if isinstance(exc, EngineError) else "MODEL_LOAD_FAILED",
                }
            ),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
