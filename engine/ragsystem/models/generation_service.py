import json

from ragsystem.domain.errors import EngineError
from ragsystem.models.generator_worker import IsolatedGenerator as LocalGenerator
from ragsystem.models.local_generator import GENERATOR_NAME
from ragsystem.models.provider import GenerationProvider
from ragsystem.models.provider_registry import ProviderRegistry
from ragsystem.storage.database import utc_now


class GenerationService:
    def __init__(self, db):
        self.db, self.generator = db, None
        self.providers = ProviderRegistry(db)

    def status(self):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT value_json FROM app_settings WHERE key='generator'"
            ).fetchone()
        config = json.loads(row[0]) if row else None
        return {
            "configured": config is not None,
            "loaded": self.generator is not None,
            "fingerprint": config["fingerprint"] if config else None,
            "candidate_only": True,
        }

    def configure(self, grant, job=None):
        grant.check()
        from ragsystem.jobs.repository import Jobs

        def check():
            if job:
                with self.db.connection() as conn:
                    Jobs.require_lease(conn, job["id"], job["lease_token"])

        generator = None
        try:
            generator = LocalGenerator(
                grant.path / GENERATOR_NAME,
                self.db.path.parent / "model-worker-logs",
                cancel_check=check,
            )
            grant.check()
            with self.db.transaction() as conn:
                if job:
                    Jobs.require_lease(conn, job["id"], job["lease_token"])
                conn.execute(
                    "INSERT INTO app_settings VALUES('generator',?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                    (
                        json.dumps(
                            {"directory": str(grant.path), "fingerprint": generator.fingerprint}
                        ),
                        utc_now(),
                    ),
                )
                if job:
                    Jobs(self.db).complete(
                        job["id"],
                        job["lease_token"],
                        "generator:approved-candidate",
                        connection=conn,
                    )
        except BaseException:
            if generator is not None:
                generator.close()
            raise
        previous, self.generator = self.generator, generator
        generator.cancel_check = None
        if previous is not None:
            previous.close()
        return self.status()

    def require(self, provider_id=None) -> GenerationProvider:
        if provider_id is not None and provider_id != "local":
            return self.providers.require(provider_id)
        if self.generator is None:
            from pathlib import Path

            from ragsystem.ipc.directories import directory_identity

            with self.db.connection() as conn:
                row = conn.execute(
                    "SELECT value_json FROM app_settings WHERE key='generator'"
                ).fetchone()
            if not row:
                raise EngineError("GENERATOR_NOT_CONFIGURED")
            config = json.loads(row[0])
            directory_identity(Path(config["directory"]))
            generator = LocalGenerator(
                Path(config["directory"]) / GENERATOR_NAME,
                self.db.path.parent / "model-worker-logs",
            )
            if generator.fingerprint != config["fingerprint"]:
                generator.close()
                raise EngineError("MODEL_FINGERPRINT_CHANGED")
            self.generator = generator
        return self.generator
