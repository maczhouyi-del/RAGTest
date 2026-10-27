import hashlib
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ipc.grants import Grants
from ragsystem.parsing.process import run_worker


def pdf(path, pages=1, text="sample", width=400, height=600):
    # Synthetic valid PDF, no downloaded or user scientific content.
    # PDFium limits one Tj string; multiple bounded strings create a genuinely large text page.
    commands = " ".join(f"({text[i:i+100]}) Tj 0 -1 Td" for i in range(0,len(text),100))
    content = f"BT /F1 1 Tf 10 590 Td {commands} ET".encode()
    page_ids = list(range(5, 5 + pages))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Count {pages} /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
    ]
    objects += [
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /Font << /F1 3 0 R >> >> /Contents 4 0 R >>".encode()
        for _ in page_ids
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    path.write_bytes(output)
    return path


@pytest.mark.parametrize(
    "case,expected",
    [("pages", "PAGE_LIMIT"), ("geometry", "PAGE_GEOMETRY_LIMIT"), ("text", "PAGE_TEXT_LIMIT")],
)
def test_actual_abnormal_pdf_limits_original_kept(tmp_path, case, expected):
    source = pdf(
        tmp_path / "synthetic.pdf",
        pages=501 if case == "pages" else 1,
        width=50000 if case == "geometry" else 400,
        text="A" * 50001 if case == "text" else "safe",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if case == "text":
        value = run_worker({"pdf_path": str(source)})
        assert value["pages"][0]["error_code"] == expected
        assert value["pages"][0]["text"] == ""
    else:
        with pytest.raises(EngineError, match=expected):
            run_worker({"pdf_path": str(source)})
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    assert run_worker({"pdf_path": str(pdf(tmp_path / "next.pdf"))})["document_page_count"] == 1


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("sleep", "PDF_WORKER_TIMEOUT"),
        ("output", "OUTPUT_LIMIT"),
        ("kill", "PDF_EXTRACTION_FAILED"),
    ],
)
def test_supervised_real_process_limits_and_cleanup(tmp_path, monkeypatch, mode, expected):
    import ragsystem.parsing.process as module

    original = subprocess.Popen
    owned = []
    monkeypatch.setenv("PRIVATE_API_CREDENTIAL", "must-not-inherit")
    code = {
        "sleep": "import time;time.sleep(60)",
        "output": "import sys,time;sys.stdout.write('x'*(9*1024*1024));sys.stdout.flush();time.sleep(60)",
        "kill": "import os;os._exit(9)",
    }[mode]

    def create(command, **kwargs):
        assert "PRIVATE_API_CREDENTIAL" not in kwargs["env"]
        child = original([sys.executable, "-c", code], **kwargs)
        owned.append(child)
        return child

    with monkeypatch.context() as patch:
        patch.setattr(module.subprocess, "Popen", create)
        with pytest.raises(EngineError, match=expected):
            run_worker(
                {"pdf_path": str(tmp_path / "unused.pdf")}, timeout=0.3 if mode == "sleep" else 5
            )
    assert len(owned) == 1 and owned[0].poll() is not None
    assert run_worker({"pdf_path": str(pdf(tmp_path / "normal.pdf"))})["document_page_count"] == 1


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX RLIMIT_CPU; Windows Job Object gate remains BLOCKED"
)
def test_actual_os_cpu_limit_terminates_child():
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from ragsystem.parsing.limits import apply_process_limits;apply_process_limits(cpu_seconds=1);exec('while True: pass')",
        ],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "engine")},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        child.wait(timeout=6)
        assert child.returncode in {-signal.SIGKILL, -signal.SIGXCPU}
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_parent_path_replaced_during_open_is_rejected(tmp_path, monkeypatch):
    selected = tmp_path / "selected"
    selected.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    source = pdf(selected / "paper.pdf")
    pdf(other / "paper.pdf", text="outside")
    real_open = os.open

    def race(path, flags, *args, **kwargs):
        if Path(path) == source:
            selected.rename(tmp_path / "preserved-selected")
            selected.symlink_to(other, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    pool = Grants()
    monkeypatch.setattr(os, "open", race)
    with pytest.raises(EngineError, match="FILE_NOT_ALLOWED"):
        pool.issue(source)
    assert not pool._grants
    assert (tmp_path / "preserved-selected/paper.pdf").is_file()


def test_frozen_worker_keeps_only_named_bootloader_state(tmp_path, monkeypatch):
    import ragsystem.parsing.process as module

    original = subprocess.Popen
    monkeypatch.setattr(module.sys, "frozen", True, raising=False)
    keys = ("_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL", "_PYI_APPLICATION_HOME_DIR",
            "_PYI_LINUX_PROCESS_NAME")
    for key in keys:
        monkeypatch.setenv(key, "bootloader-fixture")
    monkeypatch.setenv("_PYI_UNRECOGNIZED_SECRET", "must-not-inherit")
    monkeypatch.setenv("PRIVATE_API_CREDENTIAL", "must-not-inherit")
    monkeypatch.setenv("HTTPS_PROXY", "must-not-inherit")

    def create(command, **kwargs):
        assert command == [sys.executable, "--parse-worker"]
        assert all(kwargs["env"][key] == "bootloader-fixture" for key in keys)
        assert not {"_PYI_UNRECOGNIZED_SECRET", "PRIVATE_API_CREDENTIAL", "HTTPS_PROXY"} & kwargs["env"].keys()
        # Real source worker validates the supervisor PID; actual frozen execution
        # is separately exercised by test_sidecar_lifecycle with the built binary.
        return original([sys.executable, "-m", "ragsystem.parsing.worker"], **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", create)
    assert run_worker({"pdf_path": str(pdf(tmp_path / "safe.pdf"))})["document_page_count"] == 1
