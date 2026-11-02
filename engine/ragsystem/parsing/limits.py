"""Resource limits are independent of filesystem/network sandboxing."""

import math
import sys

from ragsystem.domain.errors import EngineError


def apply_process_limits(cpu_seconds=240, docling=False):
    if sys.platform == "win32":
        return {"cpu": "SUPERVISOR_JOB_OBJECT", "address_space": "SUPERVISOR_JOB_OBJECT"}
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Bound each worker-created file, including stdout/stderr spool files.
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    if sys.platform == "linux":
        limit = (4 if docling else 1) * 1024**3
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    return {
        "cpu": "RLIMIT_CPU",
        "address_space": "RLIMIT_AS" if sys.platform == "linux" else "NOT_ENFORCED",
    }


def validate_page_geometry(page):
    width, height = page.get_width(), page.get_height()
    if (
        not all(math.isfinite(value) and 0 < value <= 20000 for value in (width, height))
        or width * height > 100_000_000
    ):
        raise EngineError("PAGE_GEOMETRY_LIMIT")
