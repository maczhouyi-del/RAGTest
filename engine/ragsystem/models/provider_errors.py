"""Classify only known structured codes; never retain remote error text."""

import json

from ragsystem.domain.errors import EngineError

ERROR_RESPONSE_LIMIT = 16 * 1024
CODE_GROUPS = {
    "PROVIDER_QUOTA_EXCEEDED": {
        "insufficient_quota",
        "quota_exceeded",
        "insufficient_balance",
        "arrearage",
        "balance_not_enough",
    },
    "PROVIDER_AUTH_FAILED": {
        "invalid_api_key",
        "invalid_authentication",
        "authentication_error",
        "authentication_failed",
        "invalid_token",
        "unauthorized",
    },
    "PROVIDER_PERMISSION_DENIED": {
        "permission_denied",
        "permission_error",
        "access_denied",
        "forbidden",
        "model_not_allowed",
    },
    "PROVIDER_RATE_LIMITED": {
        "rate_limit_exceeded",
        "rate_limit_error",
        "too_many_requests",
        "throttling",
    },
    "PROVIDER_SERVER_ERROR": {
        "internal_error",
        "internal_server_error",
        "server_error",
        "service_unavailable",
        "overloaded_error",
    },
}


def classify_http_error(response, path, has_body, check=None):
    raw = bytearray()
    while part := response.read1(min(4096, ERROR_RESPONSE_LIMIT + 1 - len(raw))):
        if check:
            check()
        raw.extend(part)
        if len(raw) > ERROR_RESPONSE_LIMIT:
            raise EngineError("PROVIDER_RESPONSE_LIMIT")
    try:
        value = json.loads(raw)
        error = value.get("error", {}) if isinstance(value, dict) else {}
        fields = [error.get("code"), error.get("type")] if isinstance(error, dict) else []
        # Some compatible services use a top-level stable code.
        if isinstance(value, dict):
            fields.append(value.get("code"))
        codes = {item.casefold() for item in fields if isinstance(item, str) and len(item) <= 100}
    except (ValueError, UnicodeError):
        codes = set()
    # Quota wins over generic auth/permission types, e.g. 403 insufficient_quota.
    for code, known in CODE_GROUPS.items():
        if codes & known:
            return code
    if path == "/models" and response.code in {404, 405, 501}:
        return "PROVIDER_CATALOG_UNSUPPORTED"
    if has_body and response.code in {400, 422}:
        return "PROVIDER_PARAMETER_UNSUPPORTED"
    return "PROVIDER_HTTP_ERROR"
