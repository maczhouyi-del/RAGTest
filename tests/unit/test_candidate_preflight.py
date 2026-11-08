"""Build admission checks only: synthetic files, no native build or installer claim."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def builder():
    spec = importlib.util.spec_from_file_location('candidate_builder', Path(__file__).resolve().parents[2]/'packaging/build_candidate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_and_binary_identity_checked_before_native_build(tmp_path, monkeypatch):
    module = builder()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module.sys, 'platform', 'darwin')
    monkeypatch.setattr(module.platform, 'machine', lambda:'arm64')
    source = tmp_path/'source.py'
    source.write_text('synthetic source')
    binary = tmp_path/'sidecar'
    binary.write_bytes(b'synthetic-not-executable')
    record = {'target':'aarch64-apple-darwin','path':'sidecar','sha256':module.sha(binary),
              'source_sha256':{'source.py':module.sha(source)},'model_weights_bundled':False,
              **dict.fromkeys(('vector_lab_bundled','generation_lab_bundled','ocr_lab_bundled','docling_lab_bundled'),True)}
    assert module.verify_sidecar(record)[0] == binary
    binary.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='CANDIDATE_SIDECAR_MISMATCH'):
        module.verify_sidecar(record)
    source.write_text('changed source')
    with pytest.raises(ValueError, match='CANDIDATE_SOURCE_MISMATCH'):
        module.verify_sidecar(record)
    record['vector_lab_bundled'] = False
    with pytest.raises(ValueError, match='CANDIDATE_RUNTIME_PROFILE_MISMATCH'):
        module.verify_sidecar(record)


def test_windows_requires_exact_provisioned_runtime_no_implicit_download(tmp_path):
    module = builder()
    with pytest.raises(ValueError, match='APPROVED_FIXED_WEBVIEW2_MANIFEST_REQUIRED'):
        module.webview_config(None)
    runtime = tmp_path/'fixed-runtime'
    runtime.mkdir()
    exe = runtime/'msedgewebview2.exe'
    exe.write_bytes(b'synthetic-not-executable')
    manifest = tmp_path/'webview.json'
    manifest.write_text(json.dumps({'directory':'fixed-runtime','version':'synthetic-fixture',
        'files':{'msedgewebview2.exe':hashlib.sha256(exe.read_bytes()).hexdigest()}}))
    assert module.webview_config(manifest)['webviewInstallMode']['type'] == 'fixedRuntime'
    (runtime/'unknown.dll').write_bytes(b'unlisted')
    with pytest.raises(ValueError, match='WEBVIEW2_FILE_SET_MISMATCH'):
        module.webview_config(manifest)
