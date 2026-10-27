import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ipc.server import create_app
from ragsystem.jobs.repository import Jobs
from ragsystem.library.metadata import MetadataExtraction
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from test_mvp_core import store


def test_slow_index_read_operations_busy_work_and_cancel_release(tmp_path, monkeypatch):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "base")
    entered, finish, metadata_tick = threading.Event(), threading.Event(), threading.Event()
    active = {"metadata": 0, "maximum_metadata": 0}
    original_metadata = MetadataExtraction.run_one

    def metadata(self, stopping=lambda: False):
        active["metadata"] += 1
        active["maximum_metadata"] = max(active["maximum_metadata"], active["metadata"])
        try:
            if entered.is_set():
                metadata_tick.set()
            return original_metadata(self, stopping)
        finally:
            active["metadata"] -= 1

    def slow_build(self, identifier, directory, backend, **kwargs):
        job = self.jobs.claim(identifier)
        entered.set()
        try:
            while not finish.wait(0.02):
                with self.db.connection() as conn:
                    self.jobs.require_lease(conn, identifier, job["lease_token"])
            self.jobs.complete(identifier, job["lease_token"], "fixture:index-not-published")
        except EngineError as exc:
            self.jobs.fail(identifier, job["lease_token"], exc.code)

    monkeypatch.setattr(HybridSearch, "build", slow_build)
    monkeypatch.setattr(MetadataExtraction, "run_one", metadata)
    token = "f" * 64
    with (
        TestClient(
            create_app(token, root), base_url="http://127.0.0.1", headers={"X-RAG-Session": token}
        ) as client,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        model = tmp_path / "candidate-directory"
        model.mkdir()
        directory = client.post(
            "/v0/internal/directory-grants", json={"path": str(model), "purpose": "embedding"}
        ).json()["directory_grant_id"]
        pending = executor.submit(
            client.post,
            "/v0/index",
            json={"model_grant_id": directory, "backend": "sqlite-vec", "idempotency_key": "slow"},
        )
        try:
            assert entered.wait(5)
            assert client.get("/v0/health").status_code == 200
            assert client.get("/v0/documents").status_code == 200
            search = client.post(
                "/v0/search",
                json={
                    "query": "BERT",
                    "authorized_doc_version_ids": [version],
                    "k": 3,
                    "strategy": "keyword",
                },
            )
            assert search.status_code == 200 and search.json()["results"]
            for path, body in [
                (
                    "/v0/search",
                    {
                        "query": "BERT",
                        "authorized_doc_version_ids": [version],
                        "k": 3,
                        "strategy": "hybrid",
                    },
                ),
                (
                    "/v0/answers",
                    {
                        "question": "BERT",
                        "version_ids": [version],
                        "mode": "extractive",
                        "strategy": "keyword",
                    },
                ),
                (f"/v0/documents/{version}/parse", {"idempotency_key": "busy-parse"}),
                ("/v0/imports", {"file_grant_id": "unconsumed", "idempotency_key": "busy-import"}),
            ]:
                response = client.post(path, json=body)
                assert response.status_code == 429 and response.json()["code"] == "WORKER_BUSY"
                assert response.json()["retriable"] is True
            assert metadata_tick.wait(5) and active["maximum_metadata"] == 1
            jobs = client.get("/v0/jobs").json()["jobs"]
            index = next(job for job in jobs if job["type"] == "embed_batch")
            assert len([job for job in jobs if job["type"] == "embed_batch"]) == 1
            assert client.post("/v0/jobs/" + index["job_id"] + "/cancel").status_code == 202
            assert pending.result(timeout=5).status_code == 202
            assert Jobs(db).get(index["job_id"])["status"] == "cancelled"
        finally:
            finish.set()
            pending.result(timeout=10)
        # The cancelled fixture must not hold a slot or publish a derived index.
        assert (
            client.post(
                f"/v0/documents/{version}/parse", json={"idempotency_key": "after-cancel"}
            ).status_code
            == 202
        )
        assert client.get("/v0/index").json()["ready"] is False
