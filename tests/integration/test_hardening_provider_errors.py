"""Bounded structured classification; only local HTTP fixtures, never real APIs."""

import json
import threading
import urllib.error
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.models.network_provider import NetworkProvider
from ragsystem.models.provider_registry import ProviderRegistry
from ragsystem.storage.database import Database
from test_generation_providers import values


@contextmanager
def errors(status, payload):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append(self.path)
            self.send_response(status)
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize(
    "status,remote_code,expected,retained",
    [
        (401, "invalid_api_key", "PROVIDER_AUTH_FAILED", False),
        (403, "insufficient_quota", "PROVIDER_QUOTA_EXCEEDED", True),
        (403, "permission_denied", "PROVIDER_PERMISSION_DENIED", True),
        (429, "rate_limit_exceeded", "PROVIDER_RATE_LIMITED", True),
        (500, "internal_error", "PROVIDER_SERVER_ERROR", True),
        (403, "unrecognized", "PROVIDER_HTTP_ERROR", True),
        (401, "unrecognized", "PROVIDER_HTTP_ERROR", True),
    ],
)
def test_structured_errors_preserve_key_except_known_auth(
    tmp_path, status, remote_code, expected, retained
):
    secret = "test-key-must-not-appear-in-output"
    body = json.dumps(
        {
            "error": {
                "code": remote_code,
                "type": "authentication_error"
                if remote_code == "insufficient_quota"
                else remote_code,
                "message": secret,
            }
        }
    ).encode()
    with errors(status, body) as (url, calls):
        registry = ProviderRegistry(Database(tmp_path / "data.db"))
        saved = registry.save(values(url), secret)
        with pytest.raises(EngineError) as caught:
            registry.probe(saved["id"])
        assert caught.value.code == expected and secret not in str(caught.value)
        current = registry.list()[0]
        assert current["credential_available"] is retained
        assert current["configured"] is retained
        assert current["last_error"] == expected
        assert current["connection_verified"] is False
        assert len(calls) == 1


@pytest.mark.parametrize(
    "status,payload,expected",
    [
        (500, b"not JSON -- no remote message classification", "PROVIDER_HTTP_ERROR"),
        (200, b"not JSON", "PROVIDER_RESPONSE_INVALID"),
        (403, b"x" * 17000, "PROVIDER_RESPONSE_LIMIT"),
        (200, b"x" * (1024 * 1024 + 1), "PROVIDER_RESPONSE_LIMIT"),
    ],
)
def test_malformed_and_oversized_no_body_leak(tmp_path, status, payload, expected):
    with errors(status, payload) as (url, calls):
        provider = NetworkProvider({**values(url), "revision": 1}, "key")
        with pytest.raises(EngineError, match=expected):
            provider.models()
        assert len(calls) == 1


def test_timeout_is_not_auth_or_retry():
    provider = NetworkProvider({**values("http://127.0.0.1:1/v1"), "revision": 1}, "key")
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise urllib.error.URLError(TimeoutError())

    provider._opener.open = timeout
    with pytest.raises(EngineError, match="PROVIDER_TIMEOUT"):
        provider.models()
    assert calls == [1]
