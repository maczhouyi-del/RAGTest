"""The frozen runtime may call the stdlib tracker, never an arbitrary -c string."""

import importlib.util
from pathlib import Path


def test_fixed_tracker_arguments_reject_appended_python_and_noninherited_streams():
    path = Path(__file__).resolve().parents[2] / "packaging/sidecar_entry.py"
    spec = importlib.util.spec_from_file_location("frozen_entry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    command = "from multiprocessing.resource_tracker import main;main(7)"
    assert module.resource_tracker_fd(["-B", "-c", command], ["-B"]) == 7
    for payload in [
        command + ";print('injection')",
        command.replace("7", "0"),
        command.replace("7", "2147483648"),
        "from multiprocessing.forkserver import main;main(7)",
    ]:
        assert module.resource_tracker_fd(["-c", payload], []) is None
    assert module.resource_tracker_fd(["-B", "-c", command], []) is None
