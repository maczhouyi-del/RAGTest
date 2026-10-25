"""Local HTTP protocol fixtures, not external model or scientific quality tests."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from ragsystem.domain.errors import EngineError
from ragsystem.ipc.server import create_app
from ragsystem.models.network_provider import NetworkProvider, endpoint
from ragsystem.models.provider_registry import ProviderRegistry
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.workflows.workbench import Workbench
from test_mvp_core import store


@contextmanager
def protocol_server():
    calls = []
    state = {"forged": False, "redirect": False, "identity": "magpie"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append((self.path, None, self.headers.get("Authorization")))
            status = (
                401
                if state.get("auth")
                and self.headers.get("Authorization") != "Bearer valid-test-key"
                else state.get("catalog_status", 200)
            )
            self.send_response(302 if state["redirect"] else status)
            self.send_header("Content-Type", "application/json")
            if state["redirect"]:
                self.send_header("Location", "/forbidden")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"name": state["identity"], "version": "protocol-fixture"}
                    if self.path == "/api/hello"
                    else {"data": [{"id": "protocol-fixture"}]}
                ).encode()
            )

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body, self.headers.get("Authorization")))
            if "entire claim" in body["messages"][0]["content"]:
                result = {
                    "status": "supported",
                    "reason": "protocol fixture, not quality gold",
                }
            else:
                result = {
                    "claims": [
                        {
                            "text": "Protocol fixture draft",
                            "evidence": [
                                {"citation_id": "invented" if state["forged"] else "E1"}
                            ],
                        }
                    ]
                }
            status = (
                401
                if state.get("auth")
                and self.headers.get("Authorization") != "Bearer valid-test-key"
                else state.get("post_status", 200)
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"choices": [{"message": {"content": json.dumps(result)}}]}
                ).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", calls, state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def values(url, **extra):
    return {
        "id": None,
        "name": "fixture",
        "kind": "api",
        "base_url": url,
        "model": "protocol-fixture",
        "expected_revision": 0,
        **extra,
    }


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com/v1",
        "https://name:secret@example.com/v1",
        "https://example.com/v1?key=secret",
        "http://[invalid/v1",
        "file:///v1",
        "https://example.com/v1\n",
    ],
)
def test_endpoint_rejects_unsafe_or_credential_urls(value):
    with pytest.raises(EngineError, match="PROVIDER_ENDPOINT_INVALID"):
        endpoint(value)


def test_explicit_api_consent_citations_fingerprint_and_no_secrets_in_database(
    tmp_path,
):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    app = create_app("a" * 64, root)
    with (
        protocol_server() as (url, calls, state),
        TestClient(
            app, base_url="http://127.0.0.1", headers={"X-RAG-Session": "a" * 64}
        ) as client,
    ):
        secret = "fixture-session-secret-598320"
        response = client.post(
            "/v0/generation-providers", json={**values(url), "api_key": secret}
        )
        assert response.status_code == 200, response.text
        config = response.json()
        assert secret not in response.text and calls == []
        base = {
            "question": "BERT pre-training",
            "version_ids": [version],
            "mode": "generative",
            "strategy": "keyword",
            "provider_id": config["id"],
            "provider_revision": config["revision"],
        }
        assert (
            client.post("/v0/answers", json=base).json()["code"]
            == "PROVIDER_CONSENT_REQUIRED"
        )
        assert calls == []
        assert (
            client.post(
                "/v0/answers",
                json={**base, "allow_external": True, "provider_revision": 99},
            ).json()["code"]
            == "PROVIDER_CHANGED"
        )
        probe = client.post(f"/v0/generation-providers/{config['id']}/probe")
        assert probe.json()["models"][0]["id"] == "protocol-fixture"
        assert calls[-1][1] is None
        answer = client.post(
            "/v0/answers", json={**base, "allow_external": True}
        ).json()
        run = client.get("/v0/answers/" + answer["id"]).json()
        assert run["status"] == "completed", run
        assert (
            run["claims"]
            and run["evidence"]
            and run["claims"][0]["model_support"] == "supported"
        )
        assert (
            run["result"]["model_fingerprint"]["configuration_sha256"]
            == config["fingerprint"]["configuration_sha256"]
        )
        assert all(auth == "Bearer " + secret for _, _, auth in calls)
        state["forged"] = True
        forged = client.post(
            "/v0/answers", json={**base, "allow_external": True}
        ).json()
        failed = client.get("/v0/answers/" + forged["id"]).json()
        assert (
            failed["status"] == "failed"
            and failed["error_code"] == "MODEL_OUTPUT_INVALID"
        )
        assert failed["claims"] == [] and failed["evidence"] == []
        before = len(calls)
        empty = client.post(
            "/v0/answers",
            json={**base, "question": "zzzzzznomatches", "allow_external": True},
        ).json()
        assert client.get("/v0/answers/" + empty["id"]).json()["status"] == "refused"
        assert len(calls) == before
        with db.connection() as conn:
            dump = "\n".join(conn.iterdump())
        assert secret not in dump
        assert secret.encode() not in (root / "data/research.db").read_bytes()
        restarted = ProviderRegistry(db)
        assert restarted.list()[0]["configured"] is False
        with pytest.raises(EngineError, match="PROVIDER_CREDENTIALS_REQUIRED"):
            restarted.require(config["id"])


def test_changed_provider_never_silently_uses_new_endpoint_or_local_model(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    with protocol_server() as (url, calls, state):
        registry = work.generation.providers
        config = registry.save(values(url, auth_mode="none"), "")
        run = work.create_answer(
            "BERT",
            [version],
            None,
            "generative",
            "keyword",
            provider_id=config["id"],
            allow_external=True,
            provider_revision=config["revision"],
        )
        registry.save(
            values(
                url,
                id=config["id"],
                expected_revision=config["revision"],
                model="changed",
                auth_mode="none",
            ),
            "",
        )
        work.run_answer(run["id"])
        answer = work.answers()[0]
        assert (
            answer["status"] == "failed" and answer["error_code"] == "PROVIDER_CHANGED"
        )
        assert calls == [] and work.generation.generator is None
        state["redirect"] = True
        provider = registry.require(config["id"])
        with pytest.raises(EngineError, match="PROVIDER_REDIRECT_FORBIDDEN"):
            provider.models()
        assert len(calls) == 1
        with db.connection() as conn:
            assert (
                conn.execute("SELECT count(*) FROM embedding_records").fetchone()[0]
                == 0
            )


def test_invalid_model_ids_and_response_sizes_fail_closed():
    config = {**values("http://127.0.0.1:3425/v1"), "id": "fixture", "revision": 1}
    provider = NetworkProvider(config, "")
    provider.request = lambda *args: {"data": [{"id": "bad\nmodel"}]}
    with pytest.raises(EngineError, match="PROVIDER_RESPONSE_INVALID"):
        provider.models()


def test_optional_magpie_identity_catalog_consent_and_restart(tmp_path):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    with protocol_server() as (url, calls, state):
        config = work.generation.providers.save(values(url, kind="magpie"), "")
        assert calls == []
        provider = work.generation.providers.require(config["id"])
        assert provider.models()[0]["id"] == "protocol-fixture"
        assert [item[0] for item in calls] == ["/api/hello", "/v1/models"]
        assert all(item[2] == "Bearer magpie-ragsystem" for item in calls)
        with pytest.raises(EngineError, match="PROVIDER_CONSENT_REQUIRED"):
            work.create_answer(
                "BERT",
                [version],
                None,
                "generative",
                "keyword",
                provider_id=config["id"],
                provider_revision=config["revision"],
            )
        run = work.create_answer(
            "BERT",
            [version],
            None,
            "generative",
            "keyword",
            provider_id=config["id"],
            provider_revision=config["revision"],
            allow_external=True,
        )
        work.run_answer(run["id"])
        assert work.answers()[0]["status"] == "completed"
        assert ProviderRegistry(db).require(config["id"]).models()
        state["identity"] = "other-service"
        with pytest.raises(EngineError, match="MAGPIE_IDENTITY_INVALID"):
            provider.models()
    with pytest.raises(EngineError, match="MAGPIE_LOCAL_ONLY"):
        NetworkProvider({**config, "base_url": "https://example.com/v1"}, "")
