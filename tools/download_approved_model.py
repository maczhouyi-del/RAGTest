"""Fetch only the exact candidate explicitly authorized on 2026-10-24."""

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

REPOSITORY = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILES = {
    "onnx/model.onnx",
    "tokenizer.json",
    "tokenizer_config.json",
    "config.json",
    "special_tokens_map.json",
}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            result.update(data)
    return result.hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    evidence = root / "docs/engineering/evidence/P0-implementation-2026-10-24"
    metadata = json.loads(
        (evidence / "intfloat--multilingual-e5-small.json").read_text()
    )
    assert metadata["revision"] == REVISION and metadata["card"]["license"] == "mit"
    target = root / ".tools/models" / ("intfloat-multilingual-e5-small-" + REVISION)
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for row in metadata["files"]:
        name = row["rfilename"]
        if name not in FILES:
            continue
        expected = (row.get("lfs") or {}).get("sha256")
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.stat().st_size != row["size"] or (
                expected and digest(path) != expected
            ):
                raise RuntimeError("EXISTING_MODEL_FILE_MISMATCH")
        else:
            url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}"
            for attempt in range(3):
                try:
                    temp = path.with_name(path.name + ".part-" + str(uuid4()))
                    with (
                        urllib.request.urlopen(url, timeout=60) as response,
                        temp.open("xb") as stream,
                    ):
                        total = 0
                        while data := response.read(1024 * 1024):
                            total += len(data)
                            if total > row["size"]:
                                raise RuntimeError("MODEL_SIZE_MISMATCH")
                            stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if total != row["size"] or (expected and digest(temp) != expected):
                        raise RuntimeError("MODEL_HASH_MISMATCH")
                    os.link(
                        temp, path
                    )  # Create-only publication; retain partial history.
                    break
                except (OSError, RuntimeError):
                    if attempt == 2:
                        raise
                    time.sleep(1)
        records.append(
            {"path": name, "bytes": path.stat().st_size, "sha256": digest(path)}
        )
        print(
            json.dumps({"file": name, "bytes": path.stat().st_size, "verified": True}),
            flush=True,
        )
    assert {r["path"] for r in records} == FILES
    manifest = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "license": "MIT per original model card",
        "usage": "user-authorized P0 local candidate experiment; not final model selection",
        "files": records,
        "model_path": "onnx/model.onnx",
        "tokenizer_path": "tokenizer.json",
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (evidence / "approved-model-download.json").write_text(
        json.dumps({**manifest, "directory": str(target)}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
