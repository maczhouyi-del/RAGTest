import hashlib

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ipc.grants import MAX_PDF_BYTES, Grants
from ragsystem.ipc.server import create_app


@pytest.mark.parametrize("position", [2, 16, 32])
@pytest.mark.parametrize("fault", ["format", "size", "read", "interface"])
def test_batch_rollback_only_unconsumed_owned_grants(tmp_path, monkeypatch, position, fault):
    valid = tmp_path / "valid.pdf"
    valid.write_bytes(b"%PDF-1.4\nsynthetic grant fault data\n%%EOF")
    expected = hashlib.sha256(valid.read_bytes()).hexdigest()
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a PDF" if fault == "format" else b"%PDF-1.4")
    if fault == "size":
        with broken.open("r+b") as stream:
            stream.truncate(MAX_PDF_BYTES + 1)
    pool = Grants()
    retained = pool.issue(valid)
    consumed = pool.take(pool.issue(valid).id)
    real_issue = pool.issue
    issued = []

    def inject(path):
        if path == broken and fault in {"read", "interface"}:
            if fault == "read":
                raise OSError("injected read failure")
            raise EngineError("GRANT_INTERFACE_FAILED")
        grant = real_issue(path)
        issued.append(grant)
        return grant

    monkeypatch.setattr(pool, "issue", inject)
    try:
        with pytest.raises((EngineError, OSError)):
            pool.issue_batch([valid] * (position - 1) + [broken] + [valid] * (32 - position))
        assert set(pool._grants) == {retained.id}
        assert all(grant.source.closed for grant in issued)
        assert not consumed.source.closed
        assert hashlib.sha256(valid.read_bytes()).hexdigest() == expected
        pool.revoke([retained.id, consumed.id])
        assert not consumed.source.closed
        monkeypatch.setattr(pool, "issue", real_issue)
        next_batch = pool.issue_batch([valid] * 32)
        assert len(next_batch) == 32
        assert pool.revoke([grant.id for grant in next_batch]) == 32
    finally:
        pool.close()
        consumed.source.close()


def test_atomic_ipc_grants_revoke_and_import_recovery(tmp_path):
    valid = tmp_path / "valid.pdf"
    valid.write_bytes(b"%PDF-1.4\nsynthetic storage only\n%%EOF")
    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"wrong")
    token = "d" * 64
    with TestClient(
        create_app(token, tmp_path / "store"),
        base_url="http://127.0.0.1",
        headers={"X-RAG-Session": token},
    ) as client:
        for position in [2, 16, 32]:
            response = client.post(
                "/v0/internal/file-grants/batch",
                json={"paths": [str(valid)] * (position - 1) + [str(invalid)]},
            )
            assert response.status_code == 400 and response.json()["code"] == "NOT_PDF"
        response = client.post("/v0/internal/file-grants/batch", json={"paths": [str(valid)] * 32})
        assert response.status_code == 200
        ids = [row["file_grant_id"] for row in response.json()["grants"]]
        first = client.post(
            "/v0/imports", json={"file_grant_id": ids[0], "idempotency_key": "consumed"}
        )
        assert first.status_code == 202
        revoked = client.post("/v0/internal/file-grants/revoke", json={"file_grant_ids": ids})
        assert revoked.json() == {"revoked": 31}
        assert len(client.get("/v0/documents").json()["documents"]) == 1
        assert client.post(
            "/v0/internal/file-grants/revoke", json={"file_grant_ids": ids}
        ).json() == {"revoked": 0}
        assert (
            client.post(
                "/v0/internal/file-grants/batch", json={"paths": [str(valid)] * 33}
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/v0/internal/file-grants/revoke",
                json={"file_grant_ids": ids},
                headers={"X-RAG-Session": "invalid"},
            ).status_code
            == 401
        )


def test_batch_path_envelope_is_additive_but_still_bounded(tmp_path, monkeypatch):
    from io import BytesIO

    from ragsystem.ipc.grants import FileGrant

    calls = []

    def issue(self, path):
        calls.append(path)
        return FileGrant("a" * 48, BytesIO(b""), "test.pdf", "b" * 64, 0, 0)

    monkeypatch.setattr(Grants, "issue", issue)
    token = "e" * 64
    with TestClient(
        create_app(token, tmp_path), base_url="http://127.0.0.1", headers={"X-RAG-Session": token}
    ) as client:
        # Mock only file-open for a legal-size wire envelope, not OS long-path acceptance.
        response = client.post(
            "/v0/internal/file-grants/batch", json={"paths": ["/" + "x" * 900] * 32}
        )
        assert response.status_code == 200 and len(calls) == 32
        assert (
            client.post(
                "/v0/internal/file-grants/batch", content=b" " * (128 * 1024 + 1)
            ).status_code
            == 413
        )
