"""Inventory an explicitly selected local PDF directory; no download or upload."""

import argparse
import hashlib
import json
from pathlib import Path


def inventory(directory, license_description):
    directory = Path(directory).resolve(strict=True)
    if not license_description.strip():
        raise ValueError("LICENSE_DESCRIPTION_REQUIRED")
    entries = []
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() != ".pdf" or not path.is_file():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError("CORPUS_PATH_ESCAPE")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        entries.append(
            {
                "path": str(path.resolve()),
                "sha256": digest,
                "license": license_description,
                "license_status": "user_declaration_requires_review",
                "data_kind": "real_unreviewed",
            }
        )
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--license-description", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries = inventory(args.directory, args.license_description)
    with args.output.open("x") as stream:
        json.dump(entries, stream, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "documents": len(entries),
                "scientific_quality": "BLOCKED",
                "license_review": "BLOCKED",
            }
        )
    )


if __name__ == "__main__":
    main()
