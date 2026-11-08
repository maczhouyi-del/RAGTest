from pathlib import Path

import pytest
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.workflows.history import History
from ragsystem.workflows.workbench import Workbench
from test_mvp_core import store


@pytest.mark.parametrize("turns", [1, 5])
def test_history_verifies_one_pdf_once_per_response_and_rechecks_next_response(tmp_path, monkeypatch, turns):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, "parse")
    work = Workbench(db, root, HybridSearch(db, root))
    conversation = None
    for n in range(turns):
        row = work.create_answer("BERT pre-training "+str(n), [version], None, "extractive", "keyword", conversation)
        conversation = row["conversation_id"]
        work.run_answer(row["id"])
    paper = next((root / "papers").glob("*.pdf"))
    reads = []
    original = Path.open
    def counted(self, *args, **kwargs):
        if self == paper and (args[0] if args else kwargs.get("mode", "r")) == "rb":
            reads.append(self)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "open", counted)
    result = History(work).turns(conversation)
    evidence = [e for turn in result["items"] for e in turn["evidence"]]
    assert len(evidence) > turns
    assert all(e["current_source_status"] == "verified" for e in evidence)
    assert len(reads) == 1
    original_bytes = paper.read_bytes()
    paper.write_bytes(original_bytes + b"corruption after earlier request")
    changed = History(work).turns(conversation)
    assert all(e["current_source_status"] == "stale_or_unavailable" for turn in changed["items"] for e in turn["evidence"])
