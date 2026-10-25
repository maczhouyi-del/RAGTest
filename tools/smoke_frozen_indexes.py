"""Real approved E5 and both candidate adapters inside the actual frozen sidecar."""

import json
import secrets
import sqlite3
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    directory = root / "docs/engineering/evidence/continuous-2026-10-24"
    workspace = root / ".tools/test-data" / ("frozen-indexes-中文-" + str(uuid4()))
    binary = root / "apps/desktop/src-tauri/binaries/ragsystem-engine-aarch64-apple-darwin"
    model = (
        root
        / ".tools/models/intfloat-multilingual-e5-small-614241f622f53c4eeff9890bdc4f31cfecc418b3"
    )
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
    import queue
    import threading

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
            timeout=20,
        ) as client:

            def rpc(method, path, body=None):
                response = client.request(method, path, json=body)
                response.raise_for_status()
                return response.json()

            for attempt in range(100):
                try:
                    rpc("GET", "/v0/health")
                    break
                except httpx.TransportError:
                    time.sleep(0.05)

            def wait(identifier):
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    result = rpc("GET", "/v0/jobs/" + identifier)
                    if result["status"] not in {"queued", "running"}:
                        assert result["status"] == "completed", result
                        return result
                    time.sleep(0.1)
                raise AssertionError("JOB_TIMEOUT")

            grant = rpc(
                "POST",
                "/v0/internal/file-grants",
                {"path": str(root / "tests/fixtures/public/N19-1423.pdf")},
            )
            wait(
                rpc(
                    "POST",
                    "/v0/imports",
                    {"file_grant_id": grant["file_grant_id"], "idempotency_key": "import"},
                )["job_id"]
            )
            version = rpc("GET", "/v0/documents")["documents"][0]["doc_version_id"]
            wait(
                rpc("POST", "/v0/documents/" + version + "/parse", {"idempotency_key": "parse"})[
                    "job_id"
                ]
            )
            rows = []
            for backend in ["sqlite-vec", "lancedb"]:
                grant = rpc(
                    "POST",
                    "/v0/internal/directory-grants",
                    {"path": str(model), "purpose": "embedding"},
                )
                wait(
                    rpc(
                        "POST",
                        "/v0/index",
                        {
                            "backend": backend,
                            "model_grant_id": grant["directory_grant_id"],
                            "idempotency_key": backend,
                        },
                    )["job_id"]
                )
                result = rpc(
                    "POST",
                    "/v0/search",
                    {
                        "query": "BERT pre-training tasks",
                        "strategy": "hybrid",
                        "authorized_doc_version_ids": [version],
                        "k": 5,
                    },
                )
                assert result["results"]
                for hit in result["results"]:
                    assert (
                        rpc("GET", "/v0/source-anchors/" + hit["source_anchor_id"])[
                            "doc_version_id"
                        ]
                        == version
                    )
                with sqlite3.connect(workspace / "data/research.db") as conn:
                    config = json.loads(
                        conn.execute(
                            "SELECT value_json FROM app_settings WHERE key='active_index'"
                        ).fetchone()[0]
                    )
                if backend == "lancedb":
                    assert config["new_embeddings"] == 0
                rows.append(
                    {
                        "backend": backend,
                        "hits": len(result["results"]),
                        "new_embeddings": config["new_embeddings"],
                        "reused_embeddings": config["reused_embeddings"],
                        "generation": config["generation"],
                    }
                )
            (directory / "frozen-indexes.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "workspace": str(workspace),
                        "actual_frozen_engine": True,
                        "candidate_only": True,
                        "rows": rows,
                    },
                    indent=2,
                )
                + "\n"
            )
            print(json.dumps(rows))
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
