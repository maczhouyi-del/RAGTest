"""Lock-only SBOM and optional OSV audit. Sends only public package coordinates."""

import argparse
import hashlib
import importlib.metadata
import json
import sys
import tomllib
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def components():
    locks = [
        ROOT / "engine/uv.lock",
        ROOT / "apps/desktop/package-lock.json",
        ROOT / "apps/desktop/src-tauri/Cargo.lock",
    ]
    output = []
    uv = tomllib.loads(locks[0].read_text())
    for item in uv["package"]:
        if "registry" not in item.get("source", {}):
            continue
        try:
            installed = importlib.metadata.metadata(item["name"])
            license_value = (
                installed.get("License-Expression") or installed.get("License") or "UNREVIEWED"
            )
        except importlib.metadata.PackageNotFoundError:
            license_value = "NOT_INSTALLED"
        output.append(
            {
                "name": item["name"],
                "version": item["version"],
                "ecosystem": "PyPI",
                "source": item["source"]["registry"],
                "license": license_value,
            }
        )
        for artifact in item.get("wheels", []) + ([item["sdist"]] if item.get("sdist") else []):
            if not artifact.get("hash", "").startswith("sha256:"):
                raise ValueError("PYTHON_ARTIFACT_HASH_MISSING")
    npm = json.loads(locks[1].read_text())
    for location, item in npm["packages"].items():
        if not location:
            continue
        if not item.get("integrity") or not item.get("resolved", "").startswith("https://"):
            raise ValueError("NPM_LOCK_INTEGRITY_MISSING")
        output.append(
            {
                "name": location.rsplit("node_modules/", 1)[-1],
                "version": item["version"],
                "ecosystem": "npm",
                "source": item["resolved"],
                "license": item.get("license", "UNREVIEWED"),
            }
        )
    cargo = tomllib.loads(locks[2].read_text())
    for item in cargo["package"]:
        if not item.get("source"):
            continue
        if not item.get("checksum"):
            raise ValueError("CARGO_CHECKSUM_MISSING")
        output.append(
            {
                "name": item["name"],
                "version": item["version"],
                "ecosystem": "crates.io",
                "source": item["source"],
                "license": "REQUIRES_TARGET_NOTICE_REVIEW",
            }
        )
    return output, {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in locks
    }


def audit(rows):
    unique = list({(row["ecosystem"], row["name"], row["version"]): row for row in rows}.values())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # Only coordinates from public lock entries, never source, local paths or environment.
    request = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch",
        data=json.dumps(
            {
                "queries": [
                    {
                        "package": {"name": row["name"], "ecosystem": row["ecosystem"]},
                        "version": row["version"],
                    }
                    for row in unique
                ]
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(request, timeout=30) as response:
        content = response.read(8 * 1024 * 1024 + 1)
        if len(content) > 8 * 1024 * 1024:
            raise ValueError("AUDIT_RESPONSE_LIMIT")
        result = json.loads(content)
    if len(result["results"]) != len(unique):
        raise ValueError("AUDIT_RESPONSE_MISMATCH")
    return [
        {
            "package": {key: row[key] for key in ("ecosystem", "name", "version")},
            "vulnerabilities": [v["id"] for v in entry.get("vulns", [])],
        }
        for row, entry in zip(unique, result["results"], strict=True)
        if entry.get("vulns")
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--online", action="store_true", help="Explicitly send public dependency coordinates to OSV"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows, locks = components()
    types = {"PyPI": "pypi", "npm": "npm", "crates.io": "cargo"}
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "component": {
                "type": "application",
                "name": "RAGSystem-source-locks",
                "version": "0.1.0",
            },
        },
        "components": [
            {
                "type": "library",
                "name": row["name"],
                "version": row["version"],
                "purl": f"pkg:{types[row['ecosystem']]}/{row['name'].replace('@', '%40')}@{row['version']}",
                "properties": [
                    {"name": "source", "value": row["source"]},
                    {"name": "license-review", "value": row["license"]},
                ],
            }
            for row in rows
        ],
    }
    (args.output / "source-locks.cdx.json").write_text(json.dumps(bom, indent=2) + "\n")
    record = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "lock_integrity": "PASS",
        "components": len(rows),
        "locks": locks,
        "scope": "source lock inventory, NOT release binary SBOM or legal approval",
        "license_review": "BLOCKED: target notices and model per-file license mappings require review",
        "vulnerability_audit": "NOT_EXECUTED",
    }
    code = 0
    if args.online:
        try:
            findings = audit(rows)
            record.update(vulnerability_audit="FAIL" if findings else "PASS", findings=findings)
            code = 1 if findings else 0
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            record.update(vulnerability_audit="BLOCKED", reason=type(exc).__name__)
            code = 2
    (args.output / "dependency-gate.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in record.items() if key not in {"findings", "locks"}}
        )
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
