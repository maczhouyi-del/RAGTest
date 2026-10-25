import secrets

from fastapi.testclient import TestClient
from ragsystem.ipc.server import create_app


def test_health_requires_session_and_no_secret_is_returned(tmp_path):
    token = secrets.token_hex(32)
    with TestClient(create_app(token, tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/v0/health").status_code == 401
        assert client.get("/v0/health", headers={"X-RAG-Session": "fake"}).status_code == 401
        response = client.get("/v0/health", headers={"X-RAG-Session": token})
        assert response.status_code == 200
        assert response.json()["sidecar_version"] == "0.1.0"
        assert token not in response.text
        assert client.get("/docs", headers={"X-RAG-Session": token}).status_code == 404


def test_origin_and_unknown_endpoints_are_rejected(tmp_path):
    token = secrets.token_hex(32)
    with TestClient(create_app(token, tmp_path), base_url="http://127.0.0.1") as client:
        headers = {"X-RAG-Session": token, "Origin": "https://malicious.example"}
        assert client.get("/v0/health", headers=headers).status_code == 403
        assert (
            client.post(
                "/v0/shell", headers={"X-RAG-Session": token}, json={"cmd": "x"}
            ).status_code
            == 404
        )


def test_grant_cannot_be_forged_or_reused(tmp_path):
    token = secrets.token_hex(32)
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\nsynthetic storage-only\n%%EOF")
    with TestClient(create_app(token, tmp_path / "data"), base_url="http://127.0.0.1") as client:
        headers = {"X-RAG-Session": token}
        assert (
            client.post(
                "/v0/imports",
                headers=headers,
                json={"file_grant_id": "forged", "idempotency_key": "bad"},
            ).status_code
            == 403
        )
        grant = client.post(
            "/v0/internal/file-grants", headers=headers, json={"path": str(src)}
        ).json()
        body = {"file_grant_id": grant["file_grant_id"], "idempotency_key": "ok"}
        result = client.post("/v0/imports", headers=headers, json=body)
        assert result.status_code == 202
        job_id = result.json()["job_id"]
        assert client.get("/v0/jobs/" + job_id, headers=headers).json()["status"] == "completed"
        assert (
            client.post(
                "/v0/imports",
                headers=headers,
                json={**body, "idempotency_key": "reuse"},
            ).status_code
            == 403
        )
        assert client.post("/v0/imports", headers=headers, json=body).json()["job_id"] == job_id


def test_source_change_after_grant_does_not_publish(tmp_path):
    token = secrets.token_hex(32)
    src = tmp_path / "mutable.pdf"
    src.write_bytes(b"%PDF-1.4\noriginal\n%%EOF")
    with TestClient(create_app(token, tmp_path / "data"), base_url="http://127.0.0.1") as client:
        headers = {"X-RAG-Session": token}
        grant = client.post(
            "/v0/internal/file-grants", headers=headers, json={"path": str(src)}
        ).json()
        src.write_bytes(b"%PDF-1.4\nmodified\n%%EOF")
        result = client.post(
            "/v0/imports",
            headers=headers,
            json={
                "file_grant_id": grant["file_grant_id"],
                "idempotency_key": "changed",
            },
        )
        job_id = result.json()["job_id"]
        assert client.get("/v0/jobs/" + job_id, headers=headers).json()["status"] == "failed"
        assert client.get("/v0/documents", headers=headers).json()["documents"] == []


def test_thousand_version_scope_request_has_bounded_additive_envelope(tmp_path):
    from uuid import uuid4

    token = secrets.token_hex(32)
    headers = {"X-RAG-Session": token}
    with TestClient(create_app(token, tmp_path), base_url="http://127.0.0.1") as client:
        body = {
            "query": "test",
            "strategy": "keyword",
            "authorized_doc_version_ids": [str(uuid4()) for _ in range(1000)],
            "k": 5,
        }
        response = client.post("/v0/search", headers=headers, json=body)
        assert response.status_code == 403 and response.json()["code"] == "SCOPE_NOT_AVAILABLE"
        assert (
            client.post("/v0/search", headers=headers, content=b" " * (128 * 1024 + 1)).status_code
            == 413
        )
        assert (
            client.post(
                "/v0/internal/file-grants", headers=headers, content=b" " * (16 * 1024 + 1)
            ).status_code
            == 413
        )
