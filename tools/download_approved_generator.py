"""Download only the fixed local candidate approved by the user on 2026-10-24."""

import hashlib
import json
import os
import urllib.request
from pathlib import Path
from uuid import uuid4

REPOSITORY = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
REVISION = "91cad51170dc346986eccefdc2dd33a9da36ead9"
NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
SIZE = 1117320736
SHA256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    target = root / ".tools/models" / ("qwen2.5-1.5b-instruct-gguf-" + REVISION)
    target.mkdir(parents=True, exist_ok=True)
    path = target / NAME
    if not path.exists():
        temp = target / (NAME + ".part-" + str(uuid4()))
        request = urllib.request.Request(
            f"https://hf-mirror.com/{REPOSITORY}/resolve/{REVISION}/{NAME}"
        )
        with urllib.request.urlopen(request, timeout=60) as response, temp.open("xb") as stream:
            total = 0
            while data := response.read(1024 * 1024):
                total += len(data)
                if total > SIZE:
                    raise RuntimeError("MODEL_SIZE_MISMATCH")
                stream.write(data)
                if total % (64 * 1024 * 1024) == 0:
                    print(
                        json.dumps({"downloaded_bytes": total, "expected_bytes": SIZE}), flush=True
                    )
            stream.flush()
            os.fsync(stream.fileno())
        if temp.stat().st_size != SIZE or sha(temp) != SHA256:
            raise RuntimeError("MODEL_HASH_MISMATCH")
        os.link(temp, path)
    if path.stat().st_size != SIZE or sha(path) != SHA256:
        raise RuntimeError("EXISTING_MODEL_FILE_MISMATCH")
    manifest = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "filename": NAME,
        "bytes": SIZE,
        "sha256": SHA256,
        "license": "Apache-2.0 per pinned model card",
        "transport": "hf-mirror.com redirect to official Hugging Face CDN; fixed hash verified",
        "usage": "user-approved local candidate experiment, not final model selection",
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    evidence = root / "docs/engineering/evidence/continuous-2026-10-24"
    (evidence / "approved-generator-download.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(json.dumps({"verified": True, "bytes": SIZE, "directory": str(target)}))


if __name__ == "__main__":
    main()
