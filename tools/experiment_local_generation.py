"""Real local candidate experiment; engineering evidence, never a gold evaluation."""

import hashlib
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.models.generator_worker import IsolatedGenerator as LocalGenerator
from ragsystem.models.local_generator import GENERATOR_NAME
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database
from ragsystem.workflows.workbench import Workbench


def main():
    root = Path(__file__).resolve().parents[1]
    model = Path(sys.argv[1]) / GENERATOR_NAME
    trial = root / ".tools/test-data" / ("generation-真实中文-" + str(uuid4()))
    db = Database(trial / "data/research.db")
    imported = PdfImporter(db, trial).import_path_for_test(
        root / "tests/fixtures/public/N19-1423.pdf", "import"
    )
    Parser(db, trial).parse(imported["doc_version_id"], "parse")
    work = Workbench(db, trial, HybridSearch(db, trial))
    start = time.perf_counter()
    generator = LocalGenerator(model, trial / "model-worker-logs")
    load_seconds = time.perf_counter() - start
    work.generation.generator = generator
    row = work.create_answer(
        "What are the two pre-training tasks used by BERT?",
        [imported["doc_version_id"]],
        None,
        "generative",
        "keyword_review" if "--review" in sys.argv else "keyword",
    )
    start = time.perf_counter()
    work.run_answer(row["id"])
    run = work.answers()[0]
    evidence = {
        "candidate_fingerprint": generator.fingerprint,
        "load_seconds": load_seconds,
        "answer_seconds": time.perf_counter() - start,
        "run": run,
        "workspace": str(trial),
        "scientific_quality": "NOT EVALUATED: no human gold; model support is not scientific confirmation",
        "pdf_sha256": hashlib.sha256(
            (root / "tests/fixtures/public/N19-1423.pdf").read_bytes()
        ).hexdigest(),
    }
    if "--research" in sys.argv:
        from ragsystem.jobs.repository import Jobs

        plan = work.create_plan(
            "Extract pre-training tasks only when explicitly stated",
            ["pre-training tasks"],
            [imported["doc_version_id"]],
            None,
            "generative",
        )
        job = Jobs(db).enqueue("research_extract", "real-research", {"plan_id": plan["id"]})
        research_start = time.perf_counter()
        work.execute_plan(plan["id"], job["id"])
        evidence["research_seconds"] = time.perf_counter() - research_start
        evidence["research"] = work.plans()[0]
    target = (
        root
        / "docs/engineering/evidence/continuous-2026-10-24"
        / ("generation-real-" + str(uuid4()) + ".json")
    )
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": run["status"],
                "error_code": run["error_code"],
                "claims": len(run["claims"]),
                "seconds": evidence["answer_seconds"],
                "evidence_file": str(target),
            }
        )
    )
    return 0 if run["status"] in {"completed", "refused"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
