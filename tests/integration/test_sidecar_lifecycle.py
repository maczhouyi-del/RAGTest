import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


def start_sidecar(tmp_path, command=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "engine")
    process = subprocess.Popen(
        command or [sys.executable, "-m", "ragsystem"],
        cwd=ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    token = secrets.token_hex(32)
    config = {
        "protocol_version": "0.1.0",
        "token": token,
        "data_root": str(tmp_path / "中文 空格"),
    }
    process.stdin.write((json.dumps(config) + "\n").encode())
    process.stdin.flush()
    # Selectors on pipes are Unix-only; Windows uses a bounded helper thread.
    import queue
    import threading

    messages = queue.Queue()
    threading.Thread(target=lambda: messages.put(process.stdout.readline()), daemon=True).start()
    try:
        line = messages.get(timeout=25)
        handshake = json.loads(line)
        assert handshake["protocol_version"] == "0.1.0"
        assert token.encode() not in line
        port = handshake["port"]
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=3)
        deadline = time.monotonic() + 10
        while True:
            try:
                if client.get("/v0/health", headers={"X-RAG-Session": token}).status_code == 200:
                    return process, client, token
            except httpx.TransportError:
                pass
            if time.monotonic() >= deadline:
                raise AssertionError("sidecar failed readiness")
            time.sleep(0.05)
    except BaseException:
        process.kill()
        process.wait(timeout=10)
        raise


def stop_sidecar(process):
    if process.stdin and not process.stdin.closed:
        process.stdin.close()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        raise AssertionError("broker EOF did not stop sidecar")


def test_real_child_auth_import_restart_and_eof(tmp_path):
    process, client, token = start_sidecar(tmp_path)
    try:
        assert client.get("/v0/health").status_code == 401
        assert client.get("/v0/health", headers={"X-RAG-Session": "old-session"}).status_code == 401
        headers = {"X-RAG-Session": token}
        assert (
            client.get("/v0/health", headers={**headers, "Host": "attacker.example"}).status_code
            == 403
        )
        src = tmp_path / "测试.pdf"
        src.write_bytes(b"%PDF-1.4\nsynthetic storage test only\n%%EOF")
        grant = client.post(
            "/v0/internal/file-grants", headers=headers, json={"path": str(src)}
        ).json()
        result = client.post(
            "/v0/imports",
            headers=headers,
            json={
                "file_grant_id": grant["file_grant_id"],
                "idempotency_key": "persist",
            },
        )
        assert result.status_code == 202
        job_id = result.json()["job_id"]
        deadline = time.monotonic() + 5
        while client.get("/v0/jobs/" + job_id, headers=headers).json()["status"] == "running":
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert len(client.get("/v0/documents", headers=headers).json()["documents"]) == 1
    finally:
        client.close()
        stop_sidecar(process)
    assert process.returncode == 0
    assert token.encode() not in process.stderr.read()
    process2, client2, token2 = start_sidecar(tmp_path)
    try:
        assert client2.get("/v0/health", headers={"X-RAG-Session": token}).status_code == 401
        assert (
            len(client2.get("/v0/documents", headers={"X-RAG-Session": token2}).json()["documents"])
            == 1
        )
    finally:
        client2.close()
        stop_sidecar(process2)


@pytest.mark.skipif(
    not os.environ.get("RAGSYSTEM_FROZEN_SIDECAR"), reason="Frozen binary not provided"
)
def test_frozen_sidecar_has_no_system_python_dependency(tmp_path):
    process, client, token = start_sidecar(tmp_path, [os.environ["RAGSYSTEM_FROZEN_SIDECAR"]])
    try:
        assert client.get("/v0/health", headers={"X-RAG-Session": token}).status_code == 200
    finally:
        client.close()
        stop_sidecar(process)
    assert process.returncode == 0


def test_actual_http_annotation_then_index_releases_worker_slot(tmp_path):
    command = (
        [os.environ["RAGSYSTEM_FROZEN_SIDECAR"]]
        if os.environ.get("RAGSYSTEM_FROZEN_SIDECAR")
        else None
    )
    process, client, token = start_sidecar(tmp_path, command)
    headers = {"X-RAG-Session": token}
    try:

        def post(endpoint, body):
            return client.post(endpoint, json=body, headers=headers)

        grant = post(
            "/v0/internal/file-grants", {"path": str(ROOT / "tests/fixtures/public/N19-1423.pdf")}
        ).json()
        imported = post(
            "/v0/imports",
            {"file_grant_id": grant["file_grant_id"], "idempotency_key": "http-import"},
        )
        assert imported.status_code == 202

        def wait_job(identifier):
            deadline = time.monotonic() + 20
            while True:
                row = client.get("/v0/jobs/" + identifier, headers=headers).json()
                if row["status"] not in {"running", "queued"}:
                    return row
                assert time.monotonic() < deadline
                time.sleep(0.05)

        assert wait_job(imported.json()["job_id"])["status"] == "completed"
        version = client.get("/v0/documents", headers=headers).json()["documents"][0][
            "doc_version_id"
        ]
        parsed = post("/v0/documents/" + version + "/parse", {"idempotency_key": "http-parse"})
        assert wait_job(parsed.json()["job_id"])["status"] == "completed"
        search = post(
            "/v0/search",
            {
                "query": "BERT",
                "authorized_doc_version_ids": [version],
                "k": 5,
                "strategy": "keyword",
            },
        )
        assert search.status_code == 200
        client.timeout = 10
        saved = post(
            "/v0/documents/" + version + "/annotations",
            {"page_number": 1, "note": "HTTP", "expected_revision": 0},
        )
        assert saved.status_code == 200
        directory = post(
            "/v0/internal/directory-grants", {"path": str(tmp_path), "purpose": "embedding"}
        ).json()
        indexed = post(
            "/v0/index",
            {
                "model_grant_id": directory["directory_grant_id"],
                "backend": "sqlite-vec",
                "idempotency_key": "http-index",
            },
        )
        assert indexed.status_code == 202, indexed.text
        assert (
            wait_job(indexed.json()["job_id"])["status"] == "failed"
        )  # No approved model in tmp_path.
        again = post(
            "/v0/search",
            {
                "query": "BERT",
                "authorized_doc_version_ids": [version],
                "k": 5,
                "strategy": "keyword",
            },
        )
        assert again.status_code == 200
    finally:
        client.close()
        stop_sidecar(process)


def test_crashed_engine_fences_old_task_and_preserves_original(tmp_path):
    from ragsystem.jobs.repository import Jobs
    from ragsystem.storage.database import Database

    process, client, token = start_sidecar(tmp_path)
    root = tmp_path / "中文 空格"
    db = Database(root / "data/research.db")
    jobs = Jobs(db)
    queued = jobs.enqueue("parse_page", "crash-active-task", {"doc_version_id": "test-only"})
    claimed = jobs.claim(queued["id"])
    assert claimed["status"] == "running"
    client.close()
    process.kill()
    process.wait(timeout=5)
    next_process, next_client, next_token = start_sidecar(tmp_path)
    try:
        row = next_client.get("/v0/jobs/" + queued["id"], headers={"X-RAG-Session": next_token}).json()
        assert row["status"] == "retry_wait"
        assert row["error_code"] == "ENGINE_RESTARTED"
        assert jobs.get(queued["id"])["lease_token"] is None
        assert next_client.get("/v0/health", headers={"X-RAG-Session": token}).status_code == 401
    finally:
        next_client.close()
        stop_sidecar(next_process)
