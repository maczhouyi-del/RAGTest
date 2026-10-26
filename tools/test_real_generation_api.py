"""Explicit, bounded real API smoke. Credentials enter through getpass only.

Run manually with an authorized endpoint; never use in unattended/default tests.
Only the licensed public BERT fixture may be sent as bounded excerpts.
"""

import argparse
import getpass
import hashlib
import json
import re
import sys
import time
import traceback
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.models.network_provider import NetworkProvider, endpoint
from ragsystem.models.provider_registry import ProviderRegistry
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database
from ragsystem.workflows.workbench import Workbench


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--model", help="Must be present in the authenticated model catalog"
    )
    args = parser.parse_args()
    base = endpoint(args.base_url)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    evidence = ROOT / "docs/engineering/evidence/MVP-03-2026-10-26"
    evidence.mkdir(parents=True, exist_ok=True)
    root = ROOT / ".tools/test-data" / ("real-api-" + str(uuid4()))
    record = {
        "started_at": stamp,
        "base_url": base,
        "environment": "macOS local Python engine business workflow; not native UI",
        "data_root": str(root),
        "status": "IN_PROGRESS",
        "calls": [],
        "checks": {},
        "scope": "licensed public BERT excerpts + test questions + at most 3 bounded history turns; no full PDF",
        "maximum_generation_requests": 6,
        "output_limit_per_request": 900,
        "vendor_identity": "user-specified service; not independently attested",
    }
    secret = getpass.getpass("API Key (memory only): ")
    if not secret:
        print("No credential supplied; no network request.")
        return 2

    def redact(value):
        if isinstance(value, str):
            return re.sub(
                r"sk-[A-Za-z0-9_.-]+", "[REDACTED]", value.replace(secret, "[REDACTED]")
            )
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    original = NetworkProvider.request

    def measured(provider, path, body=None):
        if provider.config["base_url"] != base:
            raise EngineError("TEST_UNAUTHORIZED_ENDPOINT")
        if (
            body is not None
            and sum(call["method"] == "POST" for call in record["calls"]) >= 6
        ):
            raise EngineError("TEST_REQUEST_BUDGET_EXHAUSTED")
        call = {"path": path, "method": "POST" if body is not None else "GET"}
        if body:
            content = json.loads(body["messages"][1]["content"])
            excerpts = content.get("excerpts", [])
            assert all(len(item["quote"]) <= 1200 for item in excerpts)
            assert len(content.get("conversation_context_not_evidence", [])) <= 3
            assert "chunks" not in content and "%PDF-" not in json.dumps(content)
            call.update(
                model=body["model"],
                task="support"
                if "entire claim" in body["messages"][0]["content"]
                else "answer",
                output_mode=provider.config.get("output_mode", "json_object"),
                input_fields=list(content),
                excerpt_count=len(excerpts),
                excerpt_characters=sum(len(item["quote"]) for item in excerpts),
                history_turns=len(content.get("conversation_context_not_evidence", [])),
                request_bytes=len(json.dumps(body, ensure_ascii=False).encode()),
            )
        opened = provider._opener.open

        def diagnostic_open(*positional, **kwargs):
            try:
                return opened(*positional, **kwargs)
            except urllib.error.HTTPError as exc:
                call["http_status"] = exc.code
                # Only a bounded, credential-redacted error is retained, never request headers.
                call["service_error"] = redact(
                    exc.read(4096).decode("utf-8", errors="replace")
                )
                raise
            except urllib.error.URLError as exc:
                call["transport_error"] = redact(str(exc.reason))[:500]
                raise

        provider._opener.open = diagnostic_open
        started = time.monotonic()
        record["calls"].append(call)
        try:
            result = original(provider, path, body)
            call.update(status="PASS", http_status=200)
            if "usage" in result:
                call["usage"] = redact(result["usage"])
            if body and result.get("choices"):
                call["finish_reason"] = result["choices"][0].get("finish_reason")
            return result
        except EngineError as exc:
            call.update(status="FAIL", code=exc.code)
            raise
        finally:
            provider._opener.open = opened
            call["seconds"] = round(time.monotonic() - started, 3)

    NetworkProvider.request = measured
    try:
        db = Database(root / "data/research.db")
        work = Workbench(db, root, HybridSearch(db, root))
        values = {
            "id": None,
            "expected_revision": 0,
            "name": "Authorized real API test",
            "kind": "api",
            "vendor": "custom",
            "auth_mode": "bearer",
            "base_url": base,
            "model": "",
            "output_mode": "json_object",
            "token_parameter": "max_tokens",
        }
        preview = work.generation.providers.preview(values, secret)
        catalog = [item["id"] for item in preview["models"]]
        record["catalog"] = catalog
        record["checks"]["model_catalog_http_success"] = (
            "PASS" if preview["connection_verified"] else "FAIL"
        )
        record["catalog_only_is_not_generation_authorization"] = True
        candidates = ["qwen-flash", "qwen-turbo", "qwen2.5-7b-instruct", "qwen-plus"]
        model = args.model or next(
            (item for item in candidates if item in catalog), None
        )
        if model not in catalog:
            raise EngineError("TEST_MODEL_SELECTION_REQUIRED")
        record["selected_model"] = model
        print(
            json.dumps(
                {
                    "catalog_count": len(catalog),
                    "selected_model": model,
                    "catalog_http": "PASS",
                }
            ),
            flush=True,
        )
        config = work.generation.providers.save(
            {
                **values,
                "model": model,
                "credential_token": preview["credential_token"],
                "enable_for_documents": True,
            },
            "",
        )
        assert config["can_answer"] and config["document_qa_enabled"]
        record["checks"]["saved_enabled_with_memory_credential"] = "PASS"
        fixture = ROOT / "tests/fixtures/public/N19-1423.pdf"
        imported = PdfImporter(db, root).import_path_for_test(fixture, "public-bert")
        version = imported["doc_version_id"]
        Parser(db, root).parse(version, "real-api-baseline")
        record["public_pdf"] = {
            "name": fixture.name,
            "sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        }
        conversation = work.create_conversation()["id"]
        answers = []
        for question in [
            "Which two pre-training tasks does BERT use? Answer only using the supplied evidence.",
            "What is the difference between these two tasks? Use the current evidence only.",
        ]:
            queued = work.create_answer(
                question,
                [version],
                None,
                "generative",
                "keyword",
                conversation,
                config["id"],
                provider_revision=config["revision"],
            )
            work.run_answer(queued["id"])
            answer = work.answers(run_id=queued["id"])[0]
            for evidence_item in answer["evidence"]:
                work.sources.anchor(evidence_item["source_anchor_id"])
            answers.append(answer)
            print(
                json.dumps(
                    {
                        "turn": len(answers),
                        "status": answer["status"],
                        "error_code": answer["error_code"],
                        "claims": len(answer["claims"]),
                        "evidence": len(answer["evidence"]),
                    }
                ),
                flush=True,
            )
            if answer["status"] != "completed":
                break
        record["answers"] = answers
        record["checks"]["cited_generation"] = (
            "PASS"
            if answers
            and all(
                a["status"] == "completed" and a["claims"] and a["evidence"]
                for a in answers
            )
            else "FAIL"
        )
        record["checks"]["two_turn_conversation"] = (
            "PASS"
            if len(answers) == 2
            and all(a["conversation_id"] == conversation for a in answers)
            else "NOT_EXECUTED"
        )
        before = len(record["calls"])
        work.generation.providers.set_authorization(
            config["id"], config["revision"], False
        )
        try:
            work.create_answer(
                "BERT",
                [version],
                None,
                "generative",
                "keyword",
                conversation,
                config["id"],
                True,
                config["revision"],
            )
            raise AssertionError("disabled provider unexpectedly accepted")
        except EngineError as exc:
            assert (
                exc.code == "PROVIDER_DOCUMENT_QA_DISABLED"
                and len(record["calls"]) == before
            )
        record["checks"]["revocation_blocks_before_network"] = "PASS"
        work.generation.providers.set_authorization(
            config["id"], config["revision"], True
        )
        restarted = ProviderRegistry(Database(db.path)).list()[0]
        assert (
            restarted["document_qa_enabled"]
            and not restarted["credential_available"]
            and not restarted["can_answer"]
        )
        record["checks"]["registry_restart_authorization_without_key"] = "PASS"
        with db.connection() as conn:
            assert secret not in "\n".join(conn.iterdump())
            assert (
                conn.execute("SELECT count(*) FROM embedding_records").fetchone()[0]
                == 0
            )
        for file in root.rglob("*"):
            if file.is_file() and file.suffix in {".db", ".db-wal", ".db-shm", ".log"}:
                assert secret.encode() not in file.read_bytes()
        record["checks"]["no_key_in_workspace_storage_or_logs"] = "PASS"
        record["status"] = (
            "PASS"
            if all(value == "PASS" for value in record["checks"].values())
            else "FAIL"
        )
        if record["status"] == "FAIL" and answers:
            record["error_code"] = (
                answers[-1]["error_code"] or "TEST_FUNCTIONAL_CHECK_FAILED"
            )
    except Exception as exc:  # noqa: BLE001 - retain only sanitized failure codes and locations
        record.update(
            status="FAIL",
            error_code=exc.code if isinstance(exc, EngineError) else type(exc).__name__,
        )
        record["failure_locations"] = [
            {"file": Path(item.filename).name, "line": item.lineno}
            for item in traceback.extract_tb(exc.__traceback__)
        ]
    finally:
        NetworkProvider.request = original
        record["finished_at"] = datetime.now(UTC).isoformat()
        serialized = json.dumps(redact(record), ensure_ascii=False, indent=2)
        assert secret not in serialized
        target = evidence / ("real-api-" + stamp + ".json")
        target.write_text(serialized + "\n")
        print(
            json.dumps(
                {
                    "status": record["status"],
                    "error_code": record.get("error_code"),
                    "checks": record["checks"],
                    "record": str(target),
                },
                ensure_ascii=False,
            )
        )
        secret = ""
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
