"""Validate the two previously approved public samples; explicit fetch for clean CI only."""

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    entries = json.loads((ROOT / "tests/fixtures/public/manifest.json").read_text())
    for item in entries:
        target = ROOT / item["path"]
        assert (
            target.parent == ROOT / "tests/fixtures/public"
            and item["url"] == "https://aclanthology.org/" + target.name
        )
        if not target.exists():
            if not args.fetch:
                raise FileNotFoundError(
                    "PUBLIC_FIXTURE_MISSING: explicit --fetch or manual provisioning required"
                )
            with urllib.request.urlopen(item["url"], timeout=30) as response:
                data = response.read(item["bytes"] + 1)
            assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"]
            temporary = target.with_name(target.name + ".part-" + str(uuid4()))
            temporary.write_bytes(data)
            os.link(temporary, target)  # create-only publication; retained staging, no deletion
        assert (
            not target.is_symlink()
            and hashlib.sha256(target.read_bytes()).hexdigest() == item["sha256"]
        )
    print(f"PASS: {len(entries)} approved public fixture hashes; no private corpus used")


if __name__ == "__main__":
    main()
