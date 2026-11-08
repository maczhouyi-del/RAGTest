import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database
from ragsystem.workflows.workbench import Workbench
from test_audit_task_contracts import versions


@pytest.mark.parametrize("question", [
    "这篇论文是否采用 systematic review 方法？",
    "What does systematic review mean in this paper?",
    'Explain the phrase "all papers" in this paper.',
    "这篇论文中 all papers 是什么意思？",
])
def test_term_or_quoted_scope_is_not_exhaustive_research(tmp_path, question):
    db = Database(tmp_path / "data/research.db")
    scope = versions(db, 1)
    run = Workbench(db, tmp_path, HybridSearch(db, tmp_path)).create_answer(question, scope, None, "extractive", "keyword")
    assert run["status"] == "queued"


@pytest.mark.parametrize("question", [
    "Summarize all papers", "Compare every paper in the library",
    "总结所有论文", "对全库逐篇审查并综合结论", "所有论文有哪些共同结论？",
])
def test_exhaustive_scope_still_requires_research(tmp_path, question):
    db = Database(tmp_path / "data/research.db")
    scope = versions(db, 1)
    with pytest.raises(EngineError, match="RESEARCH_REQUIRED"):
        Workbench(db, tmp_path, HybridSearch(db, tmp_path)).create_answer(question, scope, None, "extractive", "keyword")
