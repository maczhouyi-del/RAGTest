import os
import queue
import subprocess
import sys
import threading
from pathlib import Path


def test_worker_exits_when_supervisor_is_killed():
    """Exercise the real parent watchdog; no PDF duration or process-list guesses."""
    root = Path(__file__).resolve().parents[2]
    worker_code = (
        "import os,time; from ragsystem.parsing.worker import watch_parent; "
        "watch_parent(os.getppid()); print('WATCHING',flush=True); time.sleep(60)"
    )
    parent_code = (
        "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[1]]); "
        "time.sleep(60)"
    )
    env = {**os.environ, "PYTHONPATH": str(root / "engine")}
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_code, worker_code],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(parent.stdout.readline()), daemon=True).start()
    try:
        assert lines.get(timeout=10).strip() == b"WATCHING"
        parent.kill()
        parent.wait(timeout=5)
        threading.Thread(target=lambda: lines.put(parent.stdout.read()), daemon=True).start()
        assert lines.get(timeout=5) == b""  # inherited pipe closes only when worker ends
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
