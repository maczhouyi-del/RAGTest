"""No paid API calls: only loopback protocol servers and saved offline configs."""

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.models.network_provider import NetworkProvider
from ragsystem.models.provider_registry import ProviderRegistry
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.workflows.history import History
from ragsystem.workflows.workbench import Workbench
from test_generation_providers import protocol_server, values
from test_mvp_core import store


def test_draft_preserves_secret_for_save_but_never_persists_and_states_are_real(
    tmp_path,
):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    registry = work.generation.providers
    with protocol_server() as (url, calls, state):
        state["auth"] = True
        with pytest.raises(EngineError, match="PROVIDER_AUTH_FAILED"):
            registry.preview({"kind": "api", "base_url": url}, "invalid")
        assert not registry._drafts
        result = registry.preview({"kind": "api", "base_url": url}, "valid-test-key")
        saved = registry.save(values(url, credential_token=result["credential_token"]), "")
        assert saved["credential_available"] and saved["connection_verified"]
        assert not saved["generation_verified"]
        assert all(body is None for _, body, _ in calls)
        registry.set_authorization(saved["id"], saved["revision"], False)
        with pytest.raises(EngineError, match="PROVIDER_DOCUMENT_QA_DISABLED"):
            work.create_answer(
                "BERT",
                [version],
                None,
                "generative",
                "keyword",
                provider_id=saved["id"],
                provider_revision=saved["revision"],
            )
        registry.set_authorization(saved["id"], saved["revision"], True)
        run = work.create_answer(
            "BERT",
            [version],
            None,
            "generative",
            "keyword",
            provider_id=saved["id"],
            provider_revision=saved["revision"],
            allow_external=True,
        )
        work.run_answer(run["id"])
        assert History(work).answer(run["id"], None)["status"] == "completed"
        assert registry.list()[0]["generation_verified"]
        registry._keys[saved["id"]] = "invalid"
        with pytest.raises(EngineError, match="PROVIDER_AUTH_FAILED"):
            registry.probe(saved["id"])
        assert not registry.list()[0]["configured"]
        assert registry.list()[0]["last_error"] == "PROVIDER_AUTH_FAILED"
    with db.connection() as conn:
        dump = "\n".join(conn.iterdump())
    assert "valid-test-key" not in dump and result["credential_token"] not in dump
    restarted = ProviderRegistry(db).list()[0]
    assert (
        restarted["saved"]
        and not restarted["credential_available"]
        and not restarted["connection_verified"]
        and not restarted["generation_verified"]
    )


def test_offline_presets_empty_key_noauth_and_catalog_fallback(tmp_path):
    _root, db, _version = store(tmp_path)
    registry = ProviderRegistry(db)
    for vendor in ["deepseek", "openai"]:
        saved = registry.save(
            values(f"https://api.{vendor}.com/v1", vendor=vendor, name=vendor), ""
        )
        assert saved["saved"] and not saved["configured"]
        with pytest.raises(EngineError, match="PROVIDER_CREDENTIALS_REQUIRED"):
            registry.require(saved["id"])
    with pytest.raises(EngineError, match="PROVIDER_NOAUTH_LOCAL_ONLY"):
        registry.save(values("https://example.com/v1", auth_mode="none"), "")
    with protocol_server() as (url, _calls, state):
        state["catalog_status"] = 404
        preview = registry.preview({"kind": "api", "base_url": url, "auth_mode": "none"}, "")
        assert preview["models"] == [] and not preview["connection_verified"]
        saved = registry.save(
            values(url, auth_mode="none", credential_token=preview["credential_token"]),
            "",
        )
        assert (
            saved["configured"]
            and not saved["credential_available"]
            and not saved["connection_verified"]
        )
        assert ProviderRegistry(db).require(saved["id"])
        with pytest.raises(EngineError, match="PROVIDER_DRAFT_EXPIRED"):
            registry.save(values(url, credential_token=preview["credential_token"]), "")


@pytest.mark.parametrize(
    "output,tokens",
    [
        ("json_object", "max_tokens"),
        ("prompt_json", "max_completion_tokens"),
        ("prompt_json", "none"),
    ],
)
def test_explicit_parameter_profiles_no_fallback(output, tokens):
    with protocol_server() as (url, calls, state):
        provider = NetworkProvider(
            {
                **values(url),
                "id": "fixture",
                "revision": 1,
                "output_mode": output,
                "token_parameter": tokens,
            },
            "key",
        )
        result = provider.generate(
            "answer",
            {
                "question": "BERT",
                "chunks": [{"chunk_id": "current-source", "text": "BERT real excerpt"}],
            },
        )
        assert result["claims"][0]["evidence"][0]["chunk_id"] == "current-source"
        body = calls[-1][1]
        assert ("response_format" in body) == (output == "json_object")
        assert "temperature" not in body
        if tokens == "none":
            assert "max_tokens" not in body and "max_completion_tokens" not in body
        else:
            assert body[tokens] == 900
        state["post_status"] = 400
        before = len(calls)
        with pytest.raises(EngineError, match="PROVIDER_PARAMETER_UNSUPPORTED"):
            provider.generate(
                "answer",
                {
                    "question": "BERT",
                    "chunks": [{"chunk_id": "source", "text": "source"}],
                },
            )
        assert len(calls) == before + 1


@pytest.mark.parametrize(
    "old_prompt", ["evidence-json-v9", "evidence-json-v10-history", "evidence-json-v11-conflicts"]
)
def test_existing_local_model_prompt_upgrade_checks_all_other_fingerprints(
    tmp_path, monkeypatch, old_prompt
):
    import json

    import ragsystem.models.generation_service as module

    root, db, _version = store(tmp_path)
    directory = root / "existing-local-resource"
    directory.mkdir()
    old = {
        "model": "explicit runtime fixture",
        "runtime": "fixture",
        "weight_sha256": "fixed",
        "prompt_version": old_prompt,
    }
    new = {**old, "prompt_version": "evidence-json-v12-sources"}

    class RuntimeFixture:
        fingerprint = new
        closed = False

        def close(self):
            self.closed = True

    runtime = RuntimeFixture()
    monkeypatch.setattr(module, "LocalGenerator", lambda *args, **kwargs: runtime)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO app_settings VALUES('generator',?,'fixture')",
            (json.dumps({"directory": str(directory), "fingerprint": old}),),
        )
    service = module.GenerationService(db)
    assert service.require() is runtime
    with db.connection() as conn:
        saved = json.loads(
            conn.execute("SELECT value_json FROM app_settings WHERE key='generator'").fetchone()[0]
        )
    assert saved["fingerprint"] == new
    runtime.fingerprint = {**new, "weight_sha256": "changed"}
    with pytest.raises(EngineError, match="MODEL_FINGERPRINT_CHANGED"):
        module.GenerationService(db).require()
    assert runtime.closed
