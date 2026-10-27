import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sbom_lock_inventory_only_public_packages_and_hashes():
    rows, locks = load("dependency_gate").components()
    assert len(rows) > 500 and len(locks) == 3
    assert all(row["name"] not in {"ragsystem-engine", "ragsystem-desktop"} for row in rows)
    assert {row["ecosystem"] for row in rows} == {"PyPI", "npm", "crates.io"}
    assert all(len(sha) == 64 for sha in locks.values())


def test_ci_no_release_no_real_api_and_model_skips_explicit():
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    value = yaml.load(text, Loader=yaml.BaseLoader)
    assert value["permissions"] == {"contents": "read"}
    assert set(value["jobs"]["source"]["strategy"]["matrix"]["os"]) == {"macos-15", "windows-2025"}
    for name in [
        "upload-artifact",
        "gh release",
        "git push",
        "test_real_generation_api.py",
        "--bundles",
        "include-generation-lab",
    ]:
        assert name not in text
    assert "skips are NOT EXECUTED" in text
    assert "--extra vector-lab" in text
    assert "--online" in text


def test_malformed_osv_result_is_not_zero_vulnerabilities(monkeypatch):
    module = load("dependency_gate")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return json.dumps({"results": []}).encode()

    class Opener:
        def open(self, request, **kwargs):
            body = json.loads(request.data)
            assert body == {
                "queries": [
                    {"package": {"name": "pytest", "ecosystem": "PyPI"}, "version": "9.1.1"}
                ]
            }
            return Response()

    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(ValueError, match="AUDIT_RESPONSE_MISMATCH"):
        module.audit(
            [
                {
                    "name": "pytest",
                    "version": "9.1.1",
                    "ecosystem": "PyPI",
                    "private": "must-not-send",
                }
            ]
        )
