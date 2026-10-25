"""Public configuration in SQLite, credentials in current engine memory only."""

import secrets
import time
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.models.network_provider import NetworkProvider, definition, endpoint
from ragsystem.storage.database import utc_now


class ProviderRegistry:
    def __init__(self, db):
        self.db = db
        self._keys = {}
        self._states = {}
        self._drafts = {}

    def get(self, identifier):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM generation_providers WHERE id=?", (identifier,)
            ).fetchone()
        if row is None:
            raise EngineError("PROVIDER_NOT_FOUND", status=404)
        return dict(row)

    def list(self):
        with self.db.connection() as conn:
            rows = [
                dict(row)
                for row in conn.execute("SELECT * FROM generation_providers ORDER BY name,id")
            ]
        return [self.public(row) for row in rows]

    def public(self, row):
        state = self._states.get(row["id"], {})
        available = (
            row["kind"] == "magpie" or row["auth_mode"] == "none" or bool(self._keys.get(row["id"]))
        )
        return {
            **row,
            "saved": True,
            "configured": available,
            "credential_available": bool(self._keys.get(row["id"])),
            "connection_verified": state.get("connection_verified", False),
            "generation_verified": state.get("generation_verified", False),
            "last_error": state.get("last_error"),
            "requires_consent": True,
            "fingerprint": definition(row),
        }

    def mark_error(self, identifier, code):
        self._states.setdefault(identifier, {})["last_error"] = code
        if code == "PROVIDER_AUTH_FAILED":
            self._keys.pop(identifier, None)
            self._states[identifier].update(connection_verified=False, generation_verified=False)

    def mark_generation(self, identifier):
        self._states.setdefault(identifier, {}).update(
            connection_verified=True, generation_verified=True, last_error=None
        )

    def probe(self, identifier):
        provider = self.require(identifier)
        try:
            models = provider.models()
            self._states.setdefault(identifier, {}).update(
                connection_verified=True, last_error=None
            )
            return {"models": models, "gateway_version": provider.gateway_version}
        except EngineError as exc:
            self.mark_error(identifier, exc.code)
            raise
        finally:
            provider.close()

    @staticmethod
    def identity(values):
        return (values["kind"], endpoint(values["base_url"]), values.get("auth_mode", "bearer"))

    def preview(self, values, key):
        self._drafts = {
            token: value
            for token, value in self._drafts.items()
            if time.monotonic() - value[0] < 600
        }
        if len(self._drafts) >= 16:
            raise EngineError("PROVIDER_LIMIT")
        config = {
            "id": "connection-test",
            "name": "connection-test",
            "model": "",
            "revision": 1,
            **values,
        }
        if values.get("auth_mode", "bearer") == "bearer" and values["kind"] != "magpie" and not key:
            raise EngineError("PROVIDER_CREDENTIALS_REQUIRED", status=409)
        provider = NetworkProvider(config, key)
        verified, models, warning = False, [], None
        try:
            try:
                models = provider.models()
                verified = True
            except EngineError as exc:
                if exc.code != "PROVIDER_CATALOG_UNSUPPORTED":
                    raise
                warning = exc.code
            token = secrets.token_urlsafe(32)
            self._drafts[token] = (time.monotonic(), self.identity(values), key, verified)
            return {
                "models": models,
                "credential_token": token,
                "connection_verified": verified,
                "warning": warning,
            }
        finally:
            provider.close()

    def save(self, values, key):
        values = {**values, "base_url": endpoint(values["base_url"])}
        values = {
            "vendor": "custom",
            "auth_mode": "bearer",
            "output_mode": "json_object",
            "token_parameter": "max_tokens",
            **values,
        }
        verified = False
        credential_token = values.pop("credential_token", None)
        if credential_token:
            draft = self._drafts.get(credential_token)
            if not draft or time.monotonic() - draft[0] >= 600 or draft[1] != self.identity(values):
                raise EngineError("PROVIDER_DRAFT_EXPIRED", status=409)
            if not key:
                key, verified = draft[2], draft[3]
        if values["auth_mode"] == "none":
            key = ""
        identifier = values.get("id") or str(uuid4())
        if values["kind"] not in {"api", "magpie"}:
            raise EngineError("PROVIDER_KIND_INVALID")
        # Validate key without persisting it, even temporarily.
        NetworkProvider({**values, "id": identifier, "revision": 1}, key).close()
        with self.db.transaction() as conn:
            current = conn.execute(
                "SELECT revision FROM generation_providers WHERE id=?", (identifier,)
            ).fetchone()
            revision = current[0] if current else 0
            if values["expected_revision"] != revision:
                raise EngineError("PROVIDER_CHANGED", status=409)
            if (
                not current
                and conn.execute("SELECT COUNT(*) FROM generation_providers").fetchone()[0] >= 16
            ):
                raise EngineError("PROVIDER_LIMIT")
            conn.execute(
                "INSERT INTO generation_providers(id,name,kind,base_url,model,revision,updated_at,vendor,auth_mode,output_mode,token_parameter) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,kind=excluded.kind,base_url=excluded.base_url,model=excluded.model,revision=excluded.revision,updated_at=excluded.updated_at,vendor=excluded.vendor,auth_mode=excluded.auth_mode,output_mode=excluded.output_mode,token_parameter=excluded.token_parameter",
                (
                    identifier,
                    values["name"],
                    values["kind"],
                    values["base_url"],
                    values["model"],
                    revision + 1,
                    utc_now(),
                    values["vendor"],
                    values["auth_mode"],
                    values["output_mode"],
                    values["token_parameter"],
                ),
            )
        if key:
            self._keys[identifier] = key
        else:
            self._keys.pop(identifier, None)
        self._states[identifier] = {
            "connection_verified": verified,
            "generation_verified": False,
            "last_error": None,
        }
        if credential_token:
            self._drafts.pop(credential_token, None)
        return next(row for row in self.list() if row["id"] == identifier)

    def require(self, identifier):
        config = self.get(identifier)
        if (
            config["kind"] != "magpie"
            and config["auth_mode"] != "none"
            and not self._keys.get(identifier)
        ):
            raise EngineError("PROVIDER_CREDENTIALS_REQUIRED", status=409)
        return NetworkProvider(config, self._keys.get(identifier, ""))

    def freeze(self, identifier, allow_external, revision):
        row = self.get(identifier)
        if not allow_external:
            raise EngineError("PROVIDER_CONSENT_REQUIRED", status=403)
        if row["revision"] != revision:
            raise EngineError("PROVIDER_CHANGED", status=409)
        if (
            row["kind"] != "magpie"
            and row["auth_mode"] != "none"
            and not self._keys.get(identifier)
        ):
            raise EngineError("PROVIDER_CREDENTIALS_REQUIRED", status=409)
        return definition(row)
