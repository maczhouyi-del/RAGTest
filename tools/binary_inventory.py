"""Hash actual sidecar payloads; missing per-file license mapping blocks release."""

import argparse
import hashlib
import json
from pathlib import Path


def inventory(artifact, notices=None):
    from PyInstaller.archive.readers import CArchiveReader

    artifact = Path(artifact)
    if artifact.is_symlink() or not artifact.is_file():
        raise ValueError("ARTIFACT_INVALID")
    with artifact.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    archive = CArchiveReader(str(artifact))
    files = []
    notices = notices or {}
    for name in sorted(archive.toc):
        payload = archive.extract(name)
        sha = hashlib.sha256(payload).hexdigest()
        notice = notices.get(name, {})
        reviewed = notice.get("sha256") == sha and all(
            notice.get(key)
            for key in ("license", "source", "redistribution_obligations", "reviewer")
        )
        files.append(
            {
                "name": name,
                "sha256": sha,
                "size": len(payload),
                "type": archive.toc[name][-1],
                "license_mapping": notice if reviewed else None,
                "review": "PASS" if reviewed else "BLOCKED",
            }
        )
    return {
        "artifact": artifact.name,
        "sha256": digest,
        "kind": "actual-pyinstaller-payload-inventory",
        "files": files,
        "license_review": "PASS"
        if files and all(row["review"] == "PASS" for row in files)
        else "BLOCKED",
        "release_acceptance": "BLOCKED",
        "limitations": [
            "Python PYZ modules remain in their hashed archive; transitive and native library attribution requires review",
            "Bootloader, embedded Python and OS-linked libraries need separate provenance",
            "No signing, installer or clean-machine proof",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--notice-map", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = inventory(
        args.artifact,
        json.loads(args.notice_map.read_text()) if args.notice_map else None,
    )
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
    with args.output.with_suffix(".cdx.json").open("x") as stream:
        json.dump(cyclonedx(result), stream, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key != "files"}))
    return 2 if result["release_acceptance"] == "BLOCKED" else 0


def cyclonedx(record):
    """Actual file components, not inferred packages or a license clearance."""
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {"component": {"type": "application", "name": record['artifact'],
                      "hashes": [{"alg": "SHA-256", "content": record['sha256']}]},
                     "properties": [{"name": "release-acceptance", "value": "BLOCKED"},
                                    {"name": "inventory-scope", "value": "actual PyInstaller archive files; attribution incomplete"}]},
        "components": [{"type": "file", "name": item['name'],
                        "hashes": [{"alg": "SHA-256", "content": item['sha256']}],
                        "properties": [{"name": "license-review", "value": item['review']}]} for item in record['files']],
    }


if __name__ == "__main__":
    raise SystemExit(main())
