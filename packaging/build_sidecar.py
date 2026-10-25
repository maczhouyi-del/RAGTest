"""Freeze this platform's sidecar; never delete prior build directories."""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-vector-lab", action="store_true")
    parser.add_argument("--include-generation-lab", action="store_true")
    parser.add_argument("--include-ocr-lab", action="store_true")
    parser.add_argument("--include-docling-lab", action="store_true")
    parser.add_argument(
        "--evidence-directory", default="docs/engineering/evidence/P0-implementation-2026-10-24"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source_files = sorted(
        p for p in (root / "engine/ragsystem").rglob("*") if p.suffix in {".py", ".sql"}
    ) + [
        root / p
        for p in (
            "engine/uv.lock",
            "engine/pyproject.toml",
            "packaging/sidecar_entry.py",
            "packaging/build_sidecar.py",
        )
    ]

    def source_hashes():
        return {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source_files
        }

    frozen_sources = source_hashes()
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in {"amd64", "x86_64"}:
        target, extension = "x86_64-pc-windows-msvc", ".exe"
    elif sys.platform == "darwin" and machine == "arm64":
        target, extension = "aarch64-apple-darwin", ""
    elif sys.platform == "darwin" and machine == "x86_64":
        target, extension = "x86_64-apple-darwin", ""
    else:
        raise SystemExit("UNSUPPORTED_BUILD_TARGET")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    work = root / ".tools" / "build" / ("sidecar-" + stamp)
    work.mkdir(parents=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--name",
        "ragsystem-engine",
        "--paths",
        str(root / "engine"),
        "--collect-all",
        "ragsystem",
        "--collect-submodules",
        "uvicorn",
        "--collect-all",
        "pypdfium2_raw",
        "--hidden-import",
        "pydantic",
        "--distpath",
        str(work / "dist"),
        "--workpath",
        str(work / "work"),
        "--specpath",
        str(work),
        str(root / "packaging" / "sidecar_entry.py"),
    ]
    if not args.include_vector_lab:
        command[3:3] = [
            "--exclude-module",
            "lancedb",
            "--exclude-module",
            "pyarrow",
            "--exclude-module",
            "sqlite_vec",
            "--exclude-module",
            "onnxruntime",
            "--exclude-module",
            "tokenizers",
            "--exclude-module",
            "huggingface_hub",
            "--exclude-module",
            "hf_xet",
        ]
    else:
        command[3:3] = [
            "--collect-all",
            "onnxruntime",
            "--collect-all",
            "tokenizers",
            "--collect-all",
            "lancedb",
            "--collect-all",
            "pyarrow",
            "--collect-all",
            "sqlite_vec",
        ]
    if args.include_generation_lab:
        command[3:3] = ["--collect-all", "llama_cpp"]
    else:
        command[3:3] = ["--exclude-module", "llama_cpp"]
    if args.include_ocr_lab:
        command[3:3] = ["--collect-all", "tesserocr"]
    else:
        command[3:3] = ["--exclude-module", "tesserocr"]
    if args.include_docling_lab:
        # Optional runtime only. No model weights are bundled or downloaded.
        command[3:3] = [
            "--collect-all",
            "docling",
            "--collect-all",
            "docling_core",
            "--collect-all",
            "docling_ibm_models",
            "--collect-all",
            "transformers",
            "--collect-all",
            "torchvision",
            "--copy-metadata",
            "docling-slim",
            "--copy-metadata",
            "docling-ibm-models",
            "--copy-metadata",
            "opencv-python-headless",
        ]
    else:
        command[3:3] = [
            "--exclude-module",
            "docling",
            "--exclude-module",
            "docling_core",
            "--exclude-module",
            "docling_ibm_models",
            "--exclude-module",
            "torch",
            "--exclude-module",
            "torchvision",
            "--exclude-module",
            "transformers",
        ]
    subprocess.run(command, cwd=root, check=True)
    if source_hashes() != frozen_sources:
        raise RuntimeError(
            "SOURCE_CHANGED_DURING_BUILD: preserved build; previous binary unchanged"
        )
    binary = work / "dist" / ("ragsystem-engine" + extension)
    destination = (
        root
        / "apps"
        / "desktop"
        / "src-tauri"
        / "binaries"
        / ("ragsystem-engine-" + target + extension)
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, destination)
    sha = hashlib.sha256(destination.read_bytes()).hexdigest()
    record = {
        "built_at": stamp,
        "target": target,
        "python": sys.version,
        "argv": command,
        "path": str(destination.relative_to(root)),
        "sha256": sha,
        "bytes": destination.stat().st_size,
        "windows_install_verified": False,
        "vector_lab_bundled": args.include_vector_lab,
        "generation_lab_bundled": args.include_generation_lab,
        "ocr_lab_bundled": args.include_ocr_lab,
        "docling_lab_bundled": args.include_docling_lab,
        "model_weights_bundled": False,
        "source_sha256": frozen_sources,
    }
    (work / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    evidence = root / args.evidence_directory
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / ("sidecar-" + stamp + ".json")).write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
