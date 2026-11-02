"""Lock-only SBOM and optional OSV audit. Sends only public package coordinates."""

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import re
import subprocess
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
                installed.get("License-Expression")
                or installed.get("License")
                or "UNREVIEWED"
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
        for artifact in item.get("wheels", []) + (
            [item["sdist"]] if item.get("sdist") else []
        ):
            if not artifact.get("hash", "").startswith("sha256:"):
                raise ValueError("PYTHON_ARTIFACT_HASH_MISSING")
    npm = json.loads(locks[1].read_text())
    for location, item in npm["packages"].items():
        if not location:
            continue
        if not item.get("integrity") or not item.get("resolved", "").startswith(
            "https://"
        ):
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
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in locks
    }


class AuditIncomplete(ValueError):
    def __init__(self, findings, reason):
        super().__init__(reason)
        self.findings = findings


def package_name(value, ecosystem):
    return re.sub(r"[-_.]+", "-", value).lower() if ecosystem == "PyPI" else value


class CurlTransport:
    """Optional local TLS transport; same public OSV payload, no shell or redirects."""
    def open(self, request, timeout=30):
        url = request if isinstance(request, str) else request.full_url
        if not re.fullmatch(r"https://api\.osv\.dev/v1/(querybatch|vulns/[A-Za-z0-9_-]+)", url):
            raise ValueError("AUDIT_URL_INVALID")
        command = ["curl", "--proto", "=https", "--fail", "--silent", "--show-error", "--max-time", str(timeout), "--max-filesize", str(8 * 1024 * 1024)]
        data = None if isinstance(request, str) else request.data
        if data is not None:
            command += ["-H", "Content-Type: application/json", "--data-binary", "@-"]
        result = subprocess.run(command + [url], input=data, capture_output=True, timeout=timeout + 5)
        if result.returncode:
            raise OSError("AUDIT_TRANSPORT_FAILED")
        return io.BytesIO(result.stdout)


def audit(rows, transport="urllib"):
    unique = list(
        {(row["ecosystem"], row["name"], row["version"]): row for row in rows}.values()
    )
    opener = CurlTransport() if transport == "curl" else urllib.request.build_opener(urllib.request.ProxyHandler({}))
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
    if not isinstance(result.get("results"), list) or len(result["results"]) != len(
        unique
    ):
        raise ValueError("AUDIT_RESPONSE_MISMATCH")
    findings = []
    details = {}
    for row, entry in zip(unique, result["results"], strict=True):
        if (
            not isinstance(entry, dict)
            or entry.get("next_page_token")
            or entry.get("error")
        ):
            raise ValueError("AUDIT_INCOMPLETE")
        vulns = entry.get("vulns", [])
        if not isinstance(vulns, list):
            raise ValueError("AUDIT_RESPONSE_INVALID")
        for vuln in vulns:
            identifier = vuln.get("id")
            if not isinstance(identifier, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,160}", identifier
            ):
                raise ValueError("AUDIT_ID_INVALID")
            findings.append(
                {
                    "package": {
                        key: row[key] for key in ("ecosystem", "name", "version")
                    },
                    "vulnerability": identifier,
                    "affected": [],
                    "fixed_versions": [],
                    "source": "https://osv.dev/vulnerability/" + identifier,
                    "triage": "OPEN: locked dependency match; runtime reachability and remediation require review",
                }
            )
    detail_errors = []
    for finding in findings:
        identifier, row = finding["vulnerability"], finding["package"]
        try:
            if identifier not in details:
                with opener.open(
                    "https://api.osv.dev/v1/vulns/" + identifier, timeout=30
                ) as response:
                    data = response.read(8 * 1024 * 1024 + 1)
                    if len(data) > 8 * 1024 * 1024:
                        raise ValueError("AUDIT_RESPONSE_LIMIT")
                    details[identifier] = json.loads(data)
            detail = details[identifier]
            if detail.get("id") != identifier or not isinstance(
                detail.get("affected"), list
            ):
                raise ValueError("AUDIT_DETAIL_INVALID")
            affected = [
                item
                for item in detail["affected"]
                if package_name(
                    item.get("package", {}).get("name", ""), row["ecosystem"]
                )
                == package_name(row["name"], row["ecosystem"])
                and item.get("package", {}).get("ecosystem") == row["ecosystem"]
            ]
            if not affected:
                finding["reported_affected"] = detail["affected"]
                finding["references"] = detail.get("references", [])
                raise ValueError("AUDIT_PACKAGE_MISMATCH")
            finding.update(
                aliases=detail.get("aliases", []),
                affected=affected,
                fixed_versions=sorted(
                    {
                        event["fixed"]
                        for item in affected
                        for span in item.get("ranges", [])
                        for event in span.get("events", [])
                        if "fixed" in event
                    }
                ),
                references=detail.get("references", []),
            )
        except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired) as exc:
            reason = (
                str(exc)
                if re.fullmatch(r"AUDIT_[A-Z_]+", str(exc))
                else type(exc).__name__
            )
            finding["detail_error"] = reason
            detail_errors.append(reason)
    if detail_errors:
        raise AuditIncomplete(findings, ",".join(sorted(set(detail_errors))))
    return findings


def summary(record):
    lines = [
        "## Public dependency audit",
        "",
        "Status: " + record["vulnerability_audit"],
        "",
    ]
    for finding in record.get("findings", []):
        package = finding["package"]
        # Escape external text, including workflow command markers and Markdown links.
        text = json.dumps(
            {
                "package": package,
                "id": finding["vulnerability"],
                "affected_ranges": [{"package": item.get("package"), "ranges": item.get("ranges", []), "versions": item.get("versions", []) if not item.get("ranges") else []} for item in finding["affected"]],
                "detail_error": finding.get("detail_error"),
                "fixed_versions": finding["fixed_versions"],
                "source": finding["source"],
            },
            ensure_ascii=True,
        )
        lines.append("    " + text.replace("::", r"\u003a\u003a"))
    if record.get("reason"):
        lines.append("Blocked: " + record["reason"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--online",
        action="store_true",
        help="Explicitly send public dependency coordinates to OSV",
    )
    parser.add_argument("--transport", choices=["urllib", "curl"], default="urllib")
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
            findings = audit(rows, args.transport)
            record.update(
                vulnerability_audit="FAIL" if findings else "PASS", findings=findings
            )
            code = 1 if findings else 0
        except AuditIncomplete as exc:
            record.update(
                vulnerability_audit="BLOCKED", findings=exc.findings, reason=str(exc)
            )
            code = 2
        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            OSError,
        ) as exc:
            record.update(
                vulnerability_audit="BLOCKED",
                reason=str(exc)
                if re.fullmatch(r"AUDIT_[A-Z_]+", str(exc))
                else type(exc).__name__,
            )
            code = 2
    (args.output / "dependency-gate.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
    public_summary = summary(record)
    (args.output / "dependency-summary.md").write_text(public_summary)
    print(public_summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write(public_summary)
    print(
        json.dumps(
            {
                key: value
                for key, value in record.items()
                if key not in {"findings", "locks"}
            }
        )
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
