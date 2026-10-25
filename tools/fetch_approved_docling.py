"""Fetch only the two explicitly approved fixed Docling candidates, no runtime auto-download."""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/engineering/evidence/continuous-2026-10-24"
SOURCES = [
    (
        "docling-project/docling-layout-heron",
        "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
        "layout",
        ["config.json", "preprocessor_config.json", "model.safetensors"],
    ),
    (
        "docling-project/docling-models",
        "2199320848bb9a8a519d22e4b528185a4f9a6f64",
        "table",
        [
            "model_artifacts/tableformer/fast/tm_config.json",
            "model_artifacts/tableformer/fast/tableformer_fast.safetensors",
        ],
    ),
]


def main():
    metadata = json.loads((EVIDENCE / "docling-candidate-metadata.json").read_text())
    target = ROOT / ".tools/models/docling-heron-tableformer-fast-candidates"
    target.mkdir(parents=True, exist_ok=True)
    rows = []
    for repository, revision, kind, names in SOURCES:
        meta = metadata["layout" if kind == "layout" else "model"]
        assert meta["sha"] == revision
        files = {item["rfilename"]: item for item in meta["siblings"]}
        for name in names:
            info = files[name]
            relative = (
                "docling-project--docling-layout-heron/" + name
                if kind == "layout"
                else "docling-project--docling-models/" + name
            )
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            expected = info.get("lfs", {}).get("sha256")
            url = f"https://hf-mirror.com/{repository}/resolve/{revision}/{name}"
            if not path.exists():
                for attempt in range(3):
                    part = path.with_name(path.name + "." + str(uuid4()) + ".part")
                    try:
                        with (
                            urllib.request.urlopen(url, timeout=60) as response,
                            part.open("xb") as stream,
                        ):
                            count = 0
                            while chunk := response.read(1024 * 1024):
                                count += len(chunk)
                                if count > info["size"]:
                                    raise ValueError("RESOURCE_SIZE_MISMATCH")
                                stream.write(chunk)
                        data = part.read_bytes()
                        assert len(data) == info["size"]
                        if expected:
                            assert hashlib.sha256(data).hexdigest() == expected
                        else:
                            assert (
                                hashlib.sha1(
                                    b"blob " + str(len(data)).encode() + b"\0" + data
                                ).hexdigest()
                                == info["blobId"]
                            )
                        os.link(part, path)
                        break
                    except (OSError, urllib.error.URLError):
                        if attempt == 2:
                            raise
                        time.sleep(1)
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            assert path.stat().st_size == info["size"]
            if expected:
                assert digest == expected
            else:
                data = path.read_bytes()
                assert (
                    hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                    == info["blobId"]
                )
            record = {
                "repository": repository,
                "revision": revision,
                "file": name,
                "relative_path": relative,
                "bytes": path.stat().st_size,
                "sha256": digest,
                "git_blob_id": info["blobId"],
                "lfs_sha256_from_repository_metadata": expected,
                "download_source": url,
            }
            rows.append(record)
            print(json.dumps(record), flush=True)
    result = {
        "authorization": "User explicitly allowed both fixed candidates and project-local dependencies",
        "status": "DOWNLOADED AND VERIFIED; CANDIDATE ONLY",
        "root": str(target.relative_to(ROOT)),
        "files": rows,
        "declared_licenses": {
            "layout-heron": "Apache-2.0 model card",
            "tableformer": "repository model card lists CDLA-Permissive-2.0 and Apache-2.0; per-file assignment not supplied",
        },
        "license_texts": "docs/legal/models/docling-candidates/",
        "metadata_transport": "Official repository metadata obtained through hf-mirror because direct huggingface.co TLS fails; no independent direct-endpoint verification claim",
        "redistribution": "NOT APPROVED; local trial only",
        "model_weights_bundled": False,
    }
    (ROOT / "docs/legal/docling-model-register.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    (EVIDENCE / "approved-docling-download.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
