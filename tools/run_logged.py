"""Run a concrete local command and preserve its output, time and exit status."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--directory", default="docs/engineering/evidence/P0-implementation-2026-10-24"
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("command required")
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(result.stdout, end="")
    record = {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "cwd": str(Path.cwd()),
        "argv": command,
        "exit_code": result.returncode,
        "output": result.stdout,
    }
    name = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + args.label + ".json"
    (directory / name).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
