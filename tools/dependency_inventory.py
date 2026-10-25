"""Record local metadata and retain available license texts; not a legal approval."""

import hashlib
import importlib.metadata
import json
import re
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "docs/legal"
    destination.mkdir(parents=True, exist_ok=True)
    notices = destination / "license-texts"

    def retain(source, ecosystem, package, relative):
        target = notices / ecosystem / package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError("NOTICE_CHANGED: preserve and review old version first")
        if not target.exists():
            shutil.copyfile(source, target)
        return {
            "path": str(target.relative_to(root)),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }

    python_rows = []
    for dist in sorted(importlib.metadata.distributions(), key=lambda item: item.metadata["Name"]):
        name, version = dist.metadata["Name"], dist.version
        license_texts = []
        for relative in dist.files or []:
            if ".dist-info" in str(relative) and (
                "/licenses/" in str(relative)
                or re.match(r"^(license|copying|notice)", relative.name, re.I)
            ):
                source = Path(dist.locate_file(relative))
                if source.is_file():
                    license_texts.append(
                        retain(source, "python", name + "-" + version, Path(*relative.parts[1:]))
                    )
        python_rows.append(
            {
                "name": name,
                "version": version,
                "declared_license": dist.metadata.get("License-Expression")
                or dist.metadata.get("License"),
                "project_urls": dist.metadata.get_all("Project-URL", []),
                "license_texts": license_texts,
            }
        )

    npm = json.loads((root / "apps/desktop/package-lock.json").read_text())
    npm_rows = []
    for location, data in sorted(npm["packages"].items()):
        if not location:
            continue
        license_texts = []
        package = root / "apps/desktop" / location
        for file in package.glob("*"):
            if file.is_file() and re.match(r"^(license|copying|notice)", file.name, re.I):
                name = location.removeprefix("node_modules/").replace("/", "__")
                license_texts.append(retain(file, "npm", name + "-" + data["version"], file.name))
        npm_rows.append(
            {
                "location": location,
                "version": data.get("version"),
                "declared_license": data.get("license"),
                "source": data.get("resolved"),
                "integrity": data.get("integrity"),
                "installed_license_texts": license_texts,
            }
        )

    cargo = tomllib.loads((root / "apps/desktop/src-tauri/Cargo.lock").read_text())
    registry = root / ".tools/cargo/registry/src"
    rust_rows = []
    for data in cargo["package"]:
        name, version = data["name"], data["version"]
        candidates = list(registry.glob("*/" + name + "-" + version))
        declared, license_texts = None, []
        if candidates:
            directory = candidates[0]
            manifest = tomllib.loads((directory / "Cargo.toml").read_text())
            declared = manifest["package"].get("license")
            for file in directory.glob("*"):
                if file.is_file() and re.match(r"^(license|copying|notice)", file.name, re.I):
                    license_texts.append(retain(file, "cargo", name + "-" + version, file.name))
        rust_rows.append(
            {
                **data,
                "declared_license": declared,
                "local_source_present": bool(candidates),
                "license_texts": license_texts,
            }
        )

    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": "DRAFT — metadata inventory, not complete redistribution review",
        "scope": "Installed Mac Python environment, full npm/Cargo lock incl absent target packages; bundled binaries need separate audit",
        "python": python_rows,
        "npm": npm_rows,
        "cargo": rust_rows,
        "locks": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                root / "engine/uv.lock",
                root / "apps/desktop/package-lock.json",
                root / "apps/desktop/src-tauri/Cargo.lock",
            ]
        },
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = destination / ("dependency-inventory-" + stamp + ".json")
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "python": len(python_rows),
                "npm": len(npm_rows),
                "cargo": len(rust_rows),
            }
        )
    )


if __name__ == "__main__":
    main()
