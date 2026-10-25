"""Mac development app startup/renderer IPC/parent-death smoke; no native dialog test."""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4


def processes():
    output = subprocess.check_output(["/bin/ps", "-axo", "pid=,ppid=,comm="], text=True)
    return [
        (int(a), int(b), c)
        for line in output.splitlines()
        if len(parts := line.strip().split(None, 2)) == 3
        for a, b, c in [parts]
    ]


def main():
    root = Path(__file__).resolve().parents[1]
    executable = (
        root
        / "apps/desktop/src-tauri/target/debug/bundle/macos/RAGSystem.app/Contents/MacOS/ragsystem-desktop"
    )
    sidecar = executable.with_name("ragsystem-engine")
    if any("ragsystem-desktop" in command for _, _, command in processes()):
        raise RuntimeError("EXISTING_DESKTOP_INSTANCE: do not interrupt user session")
    run_id = str(uuid4())
    data = root / ".tools/test-data" / ("native-中文 空格-" + run_id)
    app = subprocess.Popen(
        [str(executable)],
        env={**os.environ, "RAGSYSTEM_DEV_DATA_ROOT": str(data)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    descendants = set()
    ready = False
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            assert app.poll() is None, "APP_EXITED_BEFORE_RENDERER_IPC"
            for pid, parent, command in processes():
                if parent == app.pid or parent in descendants:
                    if "ragsystem-engine" in command:
                        descendants.add(pid)
            if (data / "data/research.db").is_file() and descendants:
                ready = True
                break
            time.sleep(0.1)
        assert ready, "NATIVE_RENDERER_IPC_TIMEOUT"
    finally:
        if app.poll() is None:
            app.terminate()  # only the exact process created by this smoke
        try:
            app.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            app.kill()
            app.communicate(timeout=5)
    deadline = time.monotonic() + 12
    remaining = descendants
    while time.monotonic() < deadline:
        live = {pid for pid, _, _ in processes()}
        remaining = descendants & live
        if not remaining:
            break
        time.sleep(0.1)
    assert not remaining, "ORPHAN_SIDECAR"
    record = {
        "status": "PASS",
        "data_root": str(data),
        "native_renderer_started_sidecar": ready,
        "sidecar_pids": sorted(descendants),
        "remaining_pids": sorted(remaining),
        "application_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "sidecar_sha256": hashlib.sha256(sidecar.read_bytes()).hexdigest(),
        "scope": "Mac development app, actual WebView/Rust IPC startup and parent termination; no native dialog/import/clean-install acceptance",
    }
    output = (
        root
        / os.environ.get(
            "RAGSYSTEM_EVIDENCE_DIR", "docs/engineering/evidence/P0-implementation-2026-10-24"
        )
        / ("native-macos-" + run_id + ".json")
    )
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
