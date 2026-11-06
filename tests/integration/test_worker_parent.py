import os
import queue
import subprocess
import threading
from pathlib import Path

from process_helpers import source_python


def test_worker_exits_when_supervisor_is_killed():
    """Exercise the real parent watchdog; no PDF duration or process-list guesses."""
    root = Path(__file__).resolve().parents[2]
    worker_code = (
        "import sys,time; from ragsystem.parsing.worker import watch_parent; "
        "watch_parent(int(sys.argv[1])); print('WATCHING',flush=True); time.sleep(60)"
    )
    parent_code = (
        "import os,subprocess,sys,time; from process_helpers import source_python; "
        "exe,env=source_python(); "
        "subprocess.Popen([exe,'-c',sys.argv[1],str(os.getpid())],env=env); "
        "time.sleep(60)"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        (str(root / "engine"), str(Path(__file__).parent))
    )}
    executable, env = source_python(env)
    parent = subprocess.Popen(
        [executable, "-c", parent_code, worker_code],
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
