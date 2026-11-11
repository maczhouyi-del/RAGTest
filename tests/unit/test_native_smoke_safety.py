"""The isolated native smoke must never launch a release app against user data."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


def test_release_bundle_is_rejected_before_process_launch(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "native_smoke_safety", root / "tools/smoke_native_macos.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv(
        "RAGSYSTEM_NATIVE_APP", str(tmp_path / "release/bundle/macos/RAGSystem.app")
    )
    with patch.object(module.subprocess, "Popen") as launch:
        with pytest.raises(RuntimeError, match="DEBUG_BUNDLE_REQUIRED"):
            module.main()
        launch.assert_not_called()
