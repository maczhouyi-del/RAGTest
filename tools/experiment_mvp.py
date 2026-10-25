"""Real source/frozen PDF -> E5/sqlite-vec -> RRF -> Qwen -> exact PDF citations."""

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
    options = argparse.ArgumentParser()
    options.add_argument("--frozen", action="store_true")
    args = options.parse_args()
    root = Path(__file__).resolve().parents[1]
    evidence = root / "docs/engineering/evidence/MVP-2026-10-25"
    evidence.mkdir(parents=True, exist_ok=True)
    workspace = root / ".tools/test-data" / ("mvp-" + str(uuid4()))
    workspace.mkdir(parents=True)
    binary = root / "apps/desktop/src-tauri/binaries/ragsystem-engine-aarch64-apple-darwin"
    command = [str(binary)] if args.frozen else [sys.executable, "-m", "ragsystem"]
    token = secrets.token_hex(32)
    with (workspace / "engine.stderr.log").open("xb") as errors:
        child = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, cwd=root
        )
        messages = queue.Queue()
        threading.Thread(
            target=lambda: messages.put(child.stdout.readline(4096)), daemon=True
        ).start()
        child.stdin.write(
            (
                json.dumps(
                    {"protocol_version": "0.1.0", "token": token, "data_root": str(workspace)}
                )
                + "\n"
            ).encode()
        )
        child.stdin.flush()
        try:
            handshake = json.loads(messages.get(timeout=45))
            with httpx.Client(
                base_url=f"http://127.0.0.1:{handshake['port']}",
                headers={"X-RAG-Session": token},
                trust_env=False,
                timeout=30,
                limits=httpx.Limits(max_keepalive_connections=0),
            ) as client:

                def rpc(method, path, body=None):
                    reply = client.request(method, path, json=body)
                    reply.raise_for_status()
                    return reply.json()

                def wait(identifier):
                    deadline = time.monotonic() + 300
                    while time.monotonic() < deadline:
                        job = rpc("GET", "/v0/jobs/" + identifier)
                        if job["status"] not in {"queued", "running"}:
                            assert job["status"] == "completed", job
                            return job
                        time.sleep(0.15)
                    raise AssertionError("TASK_TIMEOUT")

                for _ in range(100):
                    try:
                        rpc("GET", "/v0/health")
                        break
                    except httpx.TransportError:
                        time.sleep(0.1)
                source = root / "tests/fixtures/public/N19-1423.pdf"
                grant = rpc("POST", "/v0/internal/file-grants", {"path": str(source)})
                wait(
                    rpc(
                        "POST",
                        "/v0/imports",
                        {"file_grant_id": grant["file_grant_id"], "idempotency_key": "bert"},
                    )["job_id"]
                )
                version = rpc("GET", "/v0/documents")["documents"][0]["doc_version_id"]
                wait(
                    rpc(
                        "POST",
                        "/v0/mvp/prepare",
                        {"version_ids": [version], "idempotency_key": "prepare"},
                    )["job_id"]
                )
                model = (
                    root
                    / ".tools/models/intfloat-multilingual-e5-small-614241f622f53c4eeff9890bdc4f31cfecc418b3"
                )
                directory = rpc(
                    "POST",
                    "/v0/internal/directory-grants",
                    {"path": str(model), "purpose": "embedding"},
                )
                wait(
                    rpc(
                        "POST",
                        "/v0/index",
                        {
                            "model_grant_id": directory["directory_grant_id"],
                            "backend": "sqlite-vec",
                            "idempotency_key": "index",
                        },
                    )["job_id"]
                )
                assert rpc("GET", "/v0/index")["ready"]
                retrieved = {
                    strategy: rpc(
                        "POST",
                        "/v0/search",
                        {
                            "query": "BERT masked language model next sentence prediction",
                            "authorized_doc_version_ids": [version],
                            "strategy": strategy,
                            "k": 8,
                        },
                    )
                    for strategy in ["keyword", "vector_exact", "hybrid"]
                }
                assert all(value["results"] for value in retrieved.values())
                generator = (
                    root
                    / ".tools/models/qwen2.5-1.5b-instruct-gguf-91cad51170dc346986eccefdc2dd33a9da36ead9"
                )
                directory = rpc(
                    "POST",
                    "/v0/internal/directory-grants",
                    {"path": str(generator), "purpose": "generator"},
                )
                wait(
                    rpc(
                        "POST",
                        "/v0/generator",
                        {
                            "model_grant_id": directory["directory_grant_id"],
                            "idempotency_key": "generator",
                        },
                    )["job_id"]
                )
                started = time.monotonic()
                answer = rpc(
                    "POST",
                    "/v0/answers",
                    {
                        "question": "Which two pre-training tasks does BERT use?",
                        "version_ids": [version],
                        "project_id": None,
                        "mode": "generative",
                        "strategy": "hybrid",
                        "conversation_id": None,
                        "per_paper_limit": 8,
                    },
                )
                wait(answer["job_id"])
                detail = rpc("GET", "/v0/answers/" + answer["id"])
                assert detail["model_history"], "GENERATION_NOT_ACTUALLY_EXECUTED"
                assert detail["evidence"], "NO_REAL_SOURCES"
                for item in detail["evidence"]:
                    anchor = rpc("GET", "/v0/source-anchors/" + item["source_anchor_id"])
                    assert anchor["file_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
                    assert anchor["bbox_norm"] is None and 1 <= anchor["page_number"] <= 16
                result = {
                    "engineering_status": "PASS",
                    "frozen": args.frozen,
                    "workspace": str(workspace),
                    "search": retrieved,
                    "answer": detail,
                    "answer_seconds": time.monotonic() - started,
                    "scientific_quality": "BLOCKED: no human gold; model output must be checked",
                    "windows_tested": False,
                }
                target = evidence / ("real-mvp-" + str(uuid4()) + ".json")
                target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                print(
                    json.dumps(
                        {
                            "engineering_status": "PASS",
                            "answer_status": detail["status"],
                            "claims": detail["claims"],
                            "evidence_count": len(detail["evidence"]),
                            "evidence_file": str(target),
                        },
                        ensure_ascii=False,
                    )
                )
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
            assert child.returncode == 0


if __name__ == "__main__":
    main()
