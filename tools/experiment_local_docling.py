"""Actual source/frozen HTTP -> supervised offline layout/table worker trial."""

import argparse
import hashlib
import json
import queue
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen", action="store_true")
    parser.add_argument("--quality-pages", action="store_true")
    parser.add_argument("--evidence-directory", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    workspace = root / ".tools/test-data" / ("docling-中文 空格-" + str(uuid4()))
    workspace.mkdir(parents=True)
    evidence = args.evidence_directory or root / "docs/engineering/evidence/continuous-2026-10-24"
    evidence.mkdir(parents=True, exist_ok=True)
    binary = root / "apps/desktop/src-tauri/binaries/ragsystem-engine-aarch64-apple-darwin"
    command = [str(binary)] if args.frozen else [sys.executable, "-m", "ragsystem"]
    token = secrets.token_hex(32)
    errors = workspace / "engine.stderr.log"
    with errors.open("xb") as log:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, cwd=root
        )
        messages = queue.Queue()
        threading.Thread(
            target=lambda: messages.put(process.stdout.readline(4096)), daemon=True
        ).start()
        process.stdin.write(
            (
                json.dumps(
                    {
                        "protocol_version": "0.1.0",
                        "token": token,
                        "data_root": str(workspace),
                    }
                )
                + "\n"
            ).encode()
        )
        process.stdin.flush()
        try:
            handshake = json.loads(messages.get(timeout=60))
            with httpx.Client(
                base_url=f"http://127.0.0.1:{handshake['port']}",
                headers={"X-RAG-Session": token},
                trust_env=False,
                limits=httpx.Limits(max_keepalive_connections=0),
                timeout=30,
            ) as client:

                def rpc(method, path, body=None):
                    response = client.request(method, path, json=body)
                    response.raise_for_status()
                    return response.json()

                def wait(identifier):
                    deadline = time.monotonic() + 330
                    while time.monotonic() < deadline:
                        job = rpc("GET", "/v0/jobs/" + identifier)
                        if job["status"] not in {"queued", "running"}:
                            assert job["status"] == "completed", job
                            return job
                        time.sleep(0.15)
                    raise AssertionError("JOB_TIMEOUT")

                for _ in range(100):
                    try:
                        rpc("GET", "/v0/health")
                        break
                    except httpx.TransportError:
                        time.sleep(0.05)
                grant = rpc(
                    "POST",
                    "/v0/internal/directory-grants",
                    {
                        "path": str(
                            root / ".tools/models/docling-heron-tableformer-fast-candidates"
                        ),
                        "purpose": "docling",
                    },
                )
                wait(
                    rpc(
                        "POST",
                        "/v0/docling",
                        {
                            "model_grant_id": grant["directory_grant_id"],
                            "idempotency_key": "layout-config",
                        },
                    )["job_id"]
                )
                records = []
                selective = []
                for filename in ("N19-1423.pdf", "2020.emnlp-main.550.pdf"):
                    source = root / "tests/fixtures/public" / filename
                    grant = rpc("POST", "/v0/internal/file-grants", {"path": str(source)})
                    wait(
                        rpc(
                            "POST",
                            "/v0/imports",
                            {
                                "file_grant_id": grant["file_grant_id"],
                                "idempotency_key": filename,
                            },
                        )["job_id"]
                    )
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                    version = next(
                        doc["doc_version_id"]
                        for doc in rpc("GET", "/v0/documents")["documents"]
                        if doc["file_sha256"] == digest
                    )
                    started = time.monotonic()
                    wait(
                        rpc(
                            "POST",
                            f"/v0/documents/{version}/parse",
                            {
                                "idempotency_key": "parse-" + filename,
                                "use_docling": True,
                            },
                        )["job_id"]
                    )
                    seconds = time.monotonic() - started
                    index = rpc("GET", f"/v0/documents/{version}/tables")
                    assert index["total"] > 0, index
                    tables = []
                    for summary in index["tables"]:
                        table = rpc("GET", "/v0/tables/" + summary["id"])
                        cells = table["cells"][:]
                        offset = table["next_row_offset"]
                        while offset is not None:
                            page = rpc("GET", f"/v0/tables/{summary['id']}?row_offset={offset}")
                            cells.extend(page["cells"])
                            offset = page["next_row_offset"]
                        table["all_cells"] = {cell["id"]: cell for cell in cells}
                        tables.append(table)
                    assert (
                        hashlib.sha256(
                            (workspace / "papers" / (digest + ".pdf")).read_bytes()
                        ).hexdigest()
                        == digest
                    )
                    records.append(
                        {
                            "filename": filename,
                            "sha256": digest,
                            "doc_version_id": version,
                            "seconds": seconds,
                            "diagnostics": rpc("GET", f"/v0/documents/{version}/parse-diagnostics"),
                            "index": index,
                            "tables": tables,
                        }
                    )
                    if args.quality_pages and filename == "N19-1423.pdf":
                        # Review an actual page-7 table; changing other pages
                        # must preserve this exact candidate/revision/cell ID.
                        candidate = next(t for t in tables if t["page_number"] == 7)
                        identifier = candidate["id"]
                        assert max(t["column_count"] for t in tables if t["page_number"] == 7) >= 5
                        rpc(
                            "POST",
                            f"/v0/tables/{identifier}/review",
                            {
                                "expected_revision": 0,
                                "status": "uncertain",
                                "note": "工程连续性核查；未作科学正确性确认",
                            },
                        )
                        reviewed = rpc("GET", f"/v0/tables/{identifier}")
                        for name, options in (
                            ("sparse-manual", {"use_docling": True, "page_numbers": [6, 8]}),
                            ("automatic", {"auto_enhance": True, "page_numbers": [6, 8]}),
                        ):
                            wait(
                                rpc(
                                    "POST",
                                    f"/v0/documents/{version}/parse",
                                    {
                                        "idempotency_key": name,
                                        **options,
                                    },
                                )["job_id"]
                            )
                            assert rpc("GET", f"/v0/tables/{identifier}") == reviewed
                            diagnostics = rpc("GET", f"/v0/documents/{version}/parse-diagnostics")
                            assert len(diagnostics["pages"]) == 16
                            assert diagnostics["runs"][0]["page_count"] == 2
                            if name == "automatic":
                                assert len(diagnostics["runs"][0]["attempts"]) == 2
                                assert all(
                                    d["method"] == "docling"
                                    for d in diagnostics["runs"][0]["routing"]
                                )
                            selective.append(
                                {
                                    "stage": name,
                                    "preserved_review": reviewed,
                                    "diagnostics": diagnostics,
                                }
                            )
                result = {
                    "status": "PASS",
                    "frozen": args.frozen,
                    "workspace": str(workspace),
                    "configuration": rpc("GET", "/v0/docling"),
                    "documents": records,
                    "selective": selective,
                    "scientific_quality": "BLOCKED: no gold set; word adapter improves sampled columns but does not certify table correctness",
                    "windows_tested": False,
                    "weights_bundled": False,
                }
                target = evidence / (
                    "docling-"
                    + ("frozen" if args.frozen else "source")
                    + "-"
                    + str(uuid4())
                    + ".json"
                )
                target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                print(
                    json.dumps(
                        {
                            "status": "PASS",
                            "evidence": str(target),
                            "documents": [
                                {
                                    "file": doc["filename"],
                                    "tables": doc["index"]["total"],
                                    "seconds": doc["seconds"],
                                    "parse_status": doc["diagnostics"]["runs"][0]["status"],
                                }
                                for doc in records
                            ],
                        }
                    )
                )
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            assert process.returncode == 0


if __name__ == "__main__":
    main()
