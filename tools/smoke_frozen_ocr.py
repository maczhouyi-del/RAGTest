"""Actual frozen sidecar OCR, resource verification and page-only source anchors."""

import hashlib
import json
import queue
import secrets
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
from experiment_local_ocr import rasterize


def main():
    root = Path(__file__).resolve().parents[1]
    workspace = root / ".tools/test-data" / ("frozen-ocr-中文 空格-" + str(uuid4()))
    workspace.mkdir(parents=True)
    scan = workspace / "BERT-page1-image-only.pdf"
    rasterize(root / "tests/fixtures/public/N19-1423.pdf", scan)
    binary = root / "apps/desktop/src-tauri/binaries/ragsystem-engine-aarch64-apple-darwin"
    process = subprocess.Popen(
        [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    token = secrets.token_hex(32)
    process.stdin.write(
        (
            json.dumps({"protocol_version": "0.1.0", "token": token, "data_root": str(workspace)})
            + "\n"
        ).encode()
    )
    process.stdin.flush()
    messages = queue.Queue()
    threading.Thread(
        target=lambda: messages.put(process.stdout.readline(4096)), daemon=True
    ).start()
    try:
        handshake = json.loads(messages.get(timeout=30))
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

            for _ in range(100):
                try:
                    rpc("GET", "/v0/health")
                    break
                except httpx.TransportError:
                    time.sleep(0.05)

            def wait(identifier):
                started = time.monotonic()
                while time.monotonic() - started < 60:
                    value = rpc("GET", "/v0/jobs/" + identifier)
                    if value["status"] not in {"queued", "running"}:
                        assert value["status"] == "completed", value
                        return value
                    time.sleep(0.1)
                raise AssertionError("JOB_TIMEOUT")

            grant = rpc("POST", "/v0/internal/file-grants", {"path": str(scan)})
            wait(
                rpc(
                    "POST",
                    "/v0/imports",
                    {"file_grant_id": grant["file_grant_id"], "idempotency_key": "import"},
                )["job_id"]
            )
            version = rpc("GET", "/v0/documents")["documents"][0]["doc_version_id"]
            wait(
                rpc("POST", f"/v0/documents/{version}/parse", {"idempotency_key": "native"})[
                    "job_id"
                ]
            )
            before = rpc("GET", f"/v0/documents/{version}/parse-diagnostics")
            assert before["needs_ocr_pages"] == [1]
            model = root / ".tools/models/tessdata-fast-65727574dfcd264acbb0c3e07860e4e9e9b22185"
            grant = rpc(
                "POST", "/v0/internal/directory-grants", {"path": str(model), "purpose": "ocr"}
            )
            wait(
                rpc(
                    "POST",
                    "/v0/ocr",
                    {
                        "model_grant_id": grant["directory_grant_id"],
                        "idempotency_key": "ocr-configure",
                    },
                )["job_id"]
            )
            started = time.monotonic()
            wait(
                rpc(
                    "POST",
                    f"/v0/documents/{version}/parse",
                    {"idempotency_key": "ocr", "use_ocr": True},
                )["job_id"]
            )
            seconds = time.monotonic() - started
            after = rpc("GET", f"/v0/documents/{version}/parse-diagnostics")
            assert (
                after["pages"][0]["quality"] == "ocr_extracted_unreviewed"
                and not after["needs_ocr_pages"]
            )
            hits = rpc(
                "POST",
                "/v0/search",
                {
                    "query": "BERT",
                    "authorized_doc_version_ids": [version],
                    "strategy": "keyword",
                    "k": 5,
                },
            )["results"]
            assert hits
            anchors = [rpc("GET", "/v0/source-anchors/" + hit["source_anchor_id"]) for hit in hits]
            digest = hashlib.sha256(scan.read_bytes()).hexdigest()
            assert all(
                anchor["file_sha256"] == digest
                and anchor["bbox_norm"] is None
                and anchor["location_level"] == "page_only"
                for anchor in anchors
            )
            record = {
                "status": "PASS",
                "actual_frozen_engine": True,
                "workspace": str(workspace),
                "derived_scan": str(scan),
                "scan_sha256": digest,
                "before": before,
                "after": after,
                "ocr_wall_seconds": seconds,
                "anchors": anchors,
                "weights_bundled": False,
                "windows_tested": False,
                "scientific_quality": "BLOCKED",
            }
            target = root / "docs/engineering/evidence/continuous-2026-10-24/frozen-ocr.json"
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "seconds": seconds,
                        "scan": str(scan),
                        "diagnostics": after["pages"],
                    },
                    ensure_ascii=False,
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
