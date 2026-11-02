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


def test_ci_npm_steps_have_explicit_directory_and_frozen_install():
    value = yaml.load((ROOT / '.github/workflows/ci.yml').read_text(), Loader=yaml.BaseLoader)
    steps = value['jobs']['source']['steps']
    npm = [step for step in steps if 'npm ' in step.get('run', '')]
    assert npm and all(step.get('working-directory') == 'apps/desktop' for step in npm)
    assert any('npm ci ' in step['run'] for step in npm)
    assert any('cargo clippy --locked' in step.get('run', '') for step in steps)


def test_local_corpus_manifest_does_not_fabricate_license_approval(tmp_path):
    module = load("local_corpus_manifest")
    (tmp_path / "sample.pdf").write_bytes(b"synthetic inventory fixture, not a scientific PDF")
    rows = module.inventory(tmp_path, "local user declaration")
    assert len(rows) == 1 and len(rows[0]["sha256"]) == 64
    assert rows[0]["license_status"] == "user_declaration_requires_review"


def test_binary_inventory_requires_hash_bound_per_file_notices(tmp_path, monkeypatch):
    from PyInstaller.archive import readers
    module = load("binary_inventory")
    artifact = tmp_path / "synthetic-sidecar"
    artifact.write_bytes(b"synthetic not executable")

    class Archive:
        toc = {"library": (0, 3, 3, 0, "b")}
        def __init__(self, path):
            pass
        def extract(self, name):
            return b"abc"

    monkeypatch.setattr(readers, "CArchiveReader", Archive)
    result = module.inventory(artifact, {"library": {"license": "MIT", "sha256": "wrong"}})
    assert result["license_review"] == "BLOCKED" and result["files"][0]["license_mapping"] is None


@pytest.mark.parametrize("detail_failure", [False, True])
def test_osv_details_include_fixed_range_and_preserve_findings_on_partial_failure(monkeypatch, detail_failure):
    module = load("dependency_gate")
    class Response:
        def __init__(self, value):
            self.value = value
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, *args):
            return json.dumps(self.value).encode()
    class Opener:
        def open(self, request, **kwargs):
            if not isinstance(request, str):
                return Response({"results": [{"vulns": [{"id": "GHSA-synthetic"}]}]})
            assert request == 'https://api.osv.dev/v1/vulns/GHSA-synthetic'
            if detail_failure:
                raise TimeoutError()
            return Response({"id": "GHSA-synthetic", "affected": [{"package": {"name": "Example_Package", "ecosystem": "PyPI"}, "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "2.0"}]}]}]})
    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *args: Opener())
    packages = [{"name": "example-package", "version": "1.0", "ecosystem": "PyPI"}]
    if detail_failure:
        with pytest.raises(module.AuditIncomplete) as result:
            module.audit(packages)
        assert result.value.findings[0]['vulnerability'] == 'GHSA-synthetic'
    else:
        findings = module.audit(packages)
        assert findings[0]['fixed_versions'] == ['2.0'] and findings[0]['affected']
        assert 'GHSA-synthetic' in module.summary({'vulnerability_audit': 'FAIL', 'findings': findings})


def test_binary_sbom_contains_actual_payload_hashes_and_no_license_approval():
    module = load('binary_inventory')
    value = module.cyclonedx({'artifact': 'fixture', 'sha256': 'a' * 64, 'files': [{'name': 'payload', 'sha256': 'b' * 64, 'review': 'BLOCKED'}]})
    assert value['bomFormat'] == 'CycloneDX'
    assert value['components'][0]['hashes'][0]['content'] == 'b' * 64
    assert value['metadata']['properties'][0]['value'] == 'BLOCKED'


def test_binary_inventory_cli_writes_sbom_and_keeps_release_blocked(tmp_path, monkeypatch):
    module = load('binary_inventory')
    output = tmp_path / 'inventory.json'
    monkeypatch.setattr('sys.argv', ['binary_inventory', '--artifact', 'fixture', '--output', str(output)])
    monkeypatch.setattr(module, 'inventory', lambda *args: {
        'artifact': 'fixture', 'sha256': 'a' * 64, 'files': [],
        'release_acceptance': 'BLOCKED',
    })
    assert module.main() == 2
    assert json.loads(output.read_text())['release_acceptance'] == 'BLOCKED'
    assert json.loads(output.with_suffix('.cdx.json').read_text())['bomFormat'] == 'CycloneDX'
