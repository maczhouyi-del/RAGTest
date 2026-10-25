"""One supervised, bounded PDF/OCR subprocess; private pipes, no shell or server."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from ragsystem.domain.errors import EngineError


def run_worker(request, *, timeout=40, check=None, log_directory=None):
    command = (
        [sys.executable, "--parse-worker"]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "ragsystem.parsing.worker"]
    )
    request = {**request, "parent_pid": os.getpid()}
    payload = json.dumps(request).encode()
    if len(payload) > 16384:
        raise EngineError("PAYLOAD_TOO_LARGE")
    environment = {**os.environ, "OMP_THREAD_LIMIT": "2", "OMP_NUM_THREADS": "2"}
    if request.get("docling_directory"):
        environment.update(
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
        )
    started = time.monotonic()
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=output, stderr=errors, env=environment
        )
        try:
            process.stdin.write(payload + b"\n")
            process.stdin.close()
            while process.poll() is None:
                if check:
                    check()
                if output.tell() > 8 * 1024 * 1024:
                    raise EngineError("OUTPUT_LIMIT")
                if errors.tell() > 4 * 1024 * 1024:
                    raise EngineError("PDF_WORKER_LOG_LIMIT")
                if time.monotonic() - started > timeout:
                    raise EngineError("PDF_WORKER_TIMEOUT")
                time.sleep(0.1)
            if check:
                check()
            if output.tell() > 8 * 1024 * 1024:
                raise EngineError("OUTPUT_LIMIT")
            output.seek(0)
            try:
                result = json.load(output)
            except (ValueError, UnicodeError) as exc:
                raise EngineError("PDF_EXTRACTION_FAILED") from exc
            if process.returncode != 0:
                code = result.get("error_code")
                allowed = {
                    "OCR_RUNTIME_NOT_PACKAGED",
                    "OCR_MODEL_HASH_MISMATCH",
                    "OCR_MODEL_NOT_AVAILABLE",
                    "OCR_FINGERPRINT_CHANGED",
                    "PAGE_LIMIT",
                    "PAGE_TEXT_LIMIT",
                    "SOURCE_PAGE_INVALID",
                    "INVALID_PARSE_PAGES",
                    "DOCLING_RUNTIME_NOT_PACKAGED",
                    "DOCLING_MODEL_NOT_AVAILABLE",
                    "DOCLING_MODEL_HASH_MISMATCH",
                    "DOCLING_FINGERPRINT_CHANGED",
                    "DOCLING_PAGE_LIMIT",
                    "DOCLING_PIXEL_LIMIT",
                    "DOCLING_INPUT_INVALID",
                    "DOCLING_CONVERSION_INCOMPLETE",
                    "DOCLING_STRUCTURE_LIMIT",
                    "DOCLING_STRUCTURE_INVALID",
                }
                raise EngineError(code if code in allowed else "PDF_EXTRACTION_FAILED")
            return result
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            errors.seek(0)
            data = errors.read(1024 * 1024 + 1)
            if log_directory is not None:
                directory = Path(log_directory)
                directory.mkdir(parents=True, exist_ok=True)
                truncated = len(data) > 1024 * 1024
                with (directory / (str(uuid4()) + ".stderr.log")).open("xb") as stream:
                    stream.write(data[: 1024 * 1024])
                    if truncated:
                        stream.write(b"\n[stderr truncated after 1 MiB]\n")
