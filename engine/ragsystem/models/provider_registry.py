"""Public configuration in SQLite, credentials in current engine memory only."""

from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.models.network_provider import NetworkProvider, definition, endpoint
from ragsystem.storage.database import utc_now


class ProviderRegistry:
    def __init__(self, db):
        self.db = db
        self._keys = {}

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
        return [
            {
                **row,
                "configured": row["kind"] == "magpie" or row["id"] in self._keys,
                "requires_consent": True,
                "fingerprint": definition(row),
            }
            for row in rows
        ]

    def save(self, values, key):
        values = {**values, "base_url": endpoint(values["base_url"])}
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
                "INSERT INTO generation_providers VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,kind=excluded.kind,base_url=excluded.base_url,model=excluded.model,revision=excluded.revision,updated_at=excluded.updated_at",
                (
                    identifier,
                    values["name"],
                    values["kind"],
                    values["base_url"],
                    values["model"],
                    revision + 1,
                    utc_now(),
                ),
            )
        self._keys[identifier] = key
        return next(row for row in self.list() if row["id"] == identifier)

    def require(self, identifier):
        config = self.get(identifier)
        if config["kind"] != "magpie" and identifier not in self._keys:
            raise EngineError("PROVIDER_CREDENTIALS_REQUIRED", status=409)
        return NetworkProvider(config, self._keys.get(identifier, ""))

    def freeze(self, identifier, allow_external, revision):
        row = self.get(identifier)
        if not allow_external:
            raise EngineError("PROVIDER_CONSENT_REQUIRED", status=403)
        if row["revision"] != revision:
            raise EngineError("PROVIDER_CHANGED", status=409)
        if row["kind"] != "magpie" and identifier not in self._keys:
            raise EngineError("PROVIDER_CREDENTIALS_REQUIRED", status=409)
        return definition(row)
