"""Small MVP endpoints keep existing authenticated application boundaries."""

from uuid import UUID

from fastapi import BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field

from ragsystem.domain.errors import EngineError
from ragsystem.models.network_provider import NetworkProvider
from ragsystem.workflows.preparation import Preparation


class PrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version_ids: list[str] = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(pattern="^(api|magpie)$")
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=0)
    api_key: str = Field(default="", max_length=4096, repr=False)


class ConnectionProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str = Field(pattern="^(api|magpie)$")
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(default="", max_length=4096, repr=False)


def register_mvp(app, db, root, search, work, jobs, slot):
    prepare = Preparation(db, root, search)

    @app.get("/v0/generation-providers")
    def providers():
        return {"providers": work.generation.providers.list()}

    @app.post("/v0/generation-provider-probe")
    def preview_provider(body: ConnectionProbe):
        provider = NetworkProvider(
            {
                "id": "connection-test",
                "name": "connection-test",
                "kind": body.kind,
                "base_url": body.base_url,
                "model": "",
                "revision": 1,
            },
            body.api_key,
        )
        try:
            models = provider.models()
            return {"models": models, "gateway_version": provider.gateway_version}
        finally:
            provider.close()

    @app.post("/v0/generation-providers")
    def save_provider(body: ProviderRequest):
        if body.id is not None:
            try:
                UUID(body.id)
            except ValueError as exc:
                raise EngineError("INVALID_REQUEST") from exc
        if any(ord(c) < 32 for c in body.name + body.model):
            raise EngineError("INVALID_REQUEST")
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            return work.generation.providers.save(
                body.model_dump(exclude={"api_key"}), body.api_key
            )
        finally:
            slot.release()

    @app.post("/v0/generation-providers/{identifier}/probe")
    def probe_provider(identifier: str):
        provider = work.generation.providers.require(identifier)
        try:
            models = provider.models()
            return {"models": models, "gateway_version": provider.gateway_version}
        finally:
            provider.close()

    def run(job_id, versions):
        try:
            prepare.run(job_id, versions)
        finally:
            slot.release()

    @app.post("/v0/mvp/prepare", status_code=202)
    def prepare_documents(body: PrepareRequest, background: BackgroundTasks):
        if len(body.version_ids) != len(set(body.version_ids)):
            raise EngineError("INVALID_REQUEST")
        with db.connection() as conn:
            work.require_scope(conn, {"project_id": None}, body.version_ids)
        if not slot.acquire(blocking=False):
            raise EngineError("WORKER_BUSY", status=429)
        try:
            row = jobs.enqueue(
                "verify",
                body.idempotency_key,
                {
                    "action": "mvp_prepare",
                    "display_name": "mvp_prepare",
                    "versions": sorted(body.version_ids),
                },
            )
            background.add_task(run, row["id"], sorted(body.version_ids))
            return {"job_id": row["id"], "status": row["status"]}
        except BaseException:
            slot.release()
            raise
