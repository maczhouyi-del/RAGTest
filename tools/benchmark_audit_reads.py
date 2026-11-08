"""Isolated old/current read-path comparison, not a scientific or capacity goldset.

Loads the trusted fixed repository baseline classes. Both versions operate on
the same temporary DB and approved public PDFs; no models or remote APIs.
"""
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import types
from contextlib import contextmanager
from pathlib import Path

from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database, utc_now
from ragsystem.workflows.history import History
from ragsystem.workflows.workbench import Workbench

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "00f8f6bc5b06889269454000f66e289b0c491f08"


def baseline_class(file, name):
    source = subprocess.check_output(["git", "show", BASELINE+":"+file], cwd=ROOT)
    module = types.ModuleType("audit_baseline_"+name)
    sys.modules[module.__name__] = module
    exec(compile(source, file, "exec"), module.__dict__)
    return getattr(module, name)


def measure(action, repeats=5):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        action()
        samples.append((time.perf_counter()-started)*1000)
    return {"samples_ms": samples, "p50_ms": statistics.median(samples), "p95_ms": max(samples)}


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    old_sources = baseline_class("engine/ragsystem/retrieval/source_search.py", "Sources")
    old_library = baseline_class("engine/ragsystem/library/repository.py", "Library")
    report = {"baseline": BASELINE, "platform": platform.platform(),
              "scope": "read-path class comparison only; warm OS cache, no physical I/O claim; no thousand-paper quality claim",
              "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) if sys.platform == "darwin" else None,
              "logical_cpu": int(subprocess.check_output(["sysctl", "-n", "hw.logicalcpu"])) if sys.platform == "darwin" else None,
              "evidence": [], "library": []}
    with tempfile.TemporaryDirectory(prefix="ragsystem-audit-benchmark-") as temporary:
        for index, fixture in enumerate(sorted((ROOT/"tests/fixtures/public").glob("*.pdf"))):
            root = Path(temporary)/str(index)
            db = Database(root/"data/research.db")
            version = PdfImporter(db, root).import_path_for_test(fixture, "public")["doc_version_id"]
            Parser(db, root).parse(version, "public")
            work = Workbench(db, root, HybridSearch(db, root))
            conversation = None
            current_anchor = work.sources.anchor
            for n in range(30):
                row = work.create_answer("BERT retrieval", [version], None, "extractive", "keyword", conversation)
                conversation = row["conversation_id"]
                work.run_answer(row["id"])
                if n not in {0, 29}:
                    continue
                def read():
                    data = History(work).turns(conversation)
                    assert sum(len(r["evidence"]) for r in data["items"]) > 0
                    assert all(e["current_source_status"] == "verified" for r in data["items"] for e in r["evidence"])
                work.sources.anchor = lambda anchor_id, **kwargs: old_sources.anchor(work.sources, anchor_id)
                before = measure(read)
                work.sources.anchor = current_anchor
                after = measure(read)
                report["evidence"].append({"fixture":fixture.name,"bytes":fixture.stat().st_size,
                    "sha256":hashlib.sha256(fixture.read_bytes()).hexdigest(),"turns":n+1,
                    "baseline":before,"current":after})
        db = Database(Path(temporary)/"synthetic/data/research.db")
        for count in (1, 50, 1000):
            with db.transaction() as conn:
                existing = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
                for n in range(existing, count):
                    digest = hashlib.sha256(str(n).encode()).hexdigest()
                    conn.execute("INSERT INTO file_assets VALUES(?,?,?,?)",(digest,10,"papers/"+digest+".pdf",utc_now()))
                    conn.execute("INSERT INTO documents VALUES(?,?,?)",(str(n),"synthetic metadata fixture",utc_now()))
                    conn.execute("INSERT INTO document_versions(id,document_id,file_sha256,visibility,created_at) VALUES(?,?,?,'visible',?)",(str(n),str(n),digest,utc_now()))
            original = db.connection
            counts = []
            @contextmanager
            def traced():
                with original() as conn:
                    conn.set_trace_callback(lambda sql: counts.append(sql) if sql.lstrip().upper().startswith("SELECT") else None)
                    yield conn
            db.connection = traced
            comparison = {}
            for name, cls in (("baseline", old_library), ("current", Library)):
                counts.clear()
                measurements = measure(lambda: cls(db).list_documents())
                comparison[name] = measurements | {"selects_per_call":len(counts)//5}
            db.connection = original
            report["library"].append({"synthetic_versions":count,**comparison})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"evidence_cases":len(report["evidence"]),"library":report["library"]}))


if __name__ == "__main__":
    run()
