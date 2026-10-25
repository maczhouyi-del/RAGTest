import secrets

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ipc.grants import MAX_PDF_BYTES, Grants
from ragsystem.ipc.server import create_app


def test_request_limit_duplicate_tokens_and_validation_redaction(tmp_path):
    token = secrets.token_hex(32)
    with TestClient(create_app(token, tmp_path), base_url="http://127.0.0.1") as client:
        headers = {"X-RAG-Session": token}
        assert client.post("/v0/imports", headers=headers, content=b"x" * 16385).status_code == 413
        assert (
            client.get(
                "/v0/health",
                headers=[("X-RAG-Session", token), ("X-RAG-Session", token)],
            ).status_code
            == 401
        )
        response = client.post(
            "/v0/imports",
            headers=headers,
            json={"path": "/private/must-not-echo-secret.pdf"},
        )
        assert response.status_code == 400
        assert "must-not-echo-secret" not in response.text


def test_symlink_and_oversized_file_are_not_granted(tmp_path):
    grants = Grants()
    large = tmp_path / "large.pdf"
    with large.open("wb") as stream:
        stream.truncate(MAX_PDF_BYTES + 1)
    with pytest.raises(EngineError, match="PDF_TOO_LARGE"):
        grants.issue(large)
    source = tmp_path / "original.pdf"
    source.write_bytes(b"%PDF-1.4\nengineering fixture")
    link = tmp_path / "link.pdf"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("Symlink creation not permitted on this host")
    with pytest.raises(EngineError, match="FILE_NOT_ALLOWED"):
        grants.issue(link)


def test_unknown_model_strategy_is_explicitly_unavailable(tmp_path):
    token = secrets.token_hex(32)
    with TestClient(create_app(token, tmp_path), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/v0/search",
            headers={"X-RAG-Session": token},
            json={
                "query": "example",
                "strategy": "vector_exact",
                "authorized_doc_version_ids": ["x"],
                "k": 5,
            },
        )
        assert response.status_code == 409
        assert response.json()["code"] == "EMBEDDING_NOT_CONFIGURED"
