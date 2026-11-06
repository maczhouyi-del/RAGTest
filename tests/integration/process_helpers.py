"""Launch the interpreter itself so process-lifecycle tests own its real PID."""

import os
import sys


def source_python(environment=None):
    environment = dict(os.environ if environment is None else environment)
    executable = sys.executable
    if sys.platform == "win32" and sys.executable != sys._base_executable:
        # Same handoff as CPython multiprocessing.popen_spawn_win32: avoid the
        # venv redirector while preserving this environment's site-packages.
        environment["__PYVENV_LAUNCHER__"] = sys.executable
        executable = sys._base_executable
    return executable, environment
