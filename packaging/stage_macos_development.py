"""Stage a fresh local development .app without removing previous bundles."""

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root / "apps/desktop/src-tauri"
template = base / "target/debug/bundle/macos/RAGSystem.app"
output = (
    root
    / ".tools/build"
    / ("macos-mvp02-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    / "RAGSystem.app"
)
output.parent.mkdir(parents=True, exist_ok=False)
shutil.copytree(template, output)
executable = output / "Contents/MacOS/ragsystem-desktop"
sidecar = output / "Contents/MacOS/ragsystem-engine"
shutil.copy2(base / "target/debug/ragsystem-desktop", executable)
shutil.copy2(base / "binaries/ragsystem-engine-aarch64-apple-darwin", sidecar)
subprocess.run(
    ["codesign", "--force", "--deep", "--sign", "-", str(output)], check=True
)
subprocess.run(["codesign", "--verify", "--deep", "--strict", str(output)], check=True)
record = {
    "app": str(output),
    "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    "sidecar_sha256": hashlib.sha256(sidecar.read_bytes()).hexdigest(),
    "scope": "local development only; ad-hoc signed, no notarization/installer/publication",
    "previous_app_preserved": str(template),
}
evidence = root / "docs/engineering/evidence/MVP-02-2026-10-25"
evidence.mkdir(parents=True, exist_ok=True)
(evidence / "macos-development-app.json").write_text(
    json.dumps(record, indent=2) + "\n"
)
print(json.dumps(record, indent=2))
