"""Real public PDFs and deterministic engineering assertions, not a gold benchmark."""

import json

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.library.repository import Library
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.document_overview import overview_topic, section_candidates
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.workflows.system_information import system_information_topic
from ragsystem.workflows.workbench import Workbench
from test_mvp_core import ROOT, store


def test_library_count_uses_database_without_retrieval_or_model(tmp_path, monkeypatch):
    root, db, version = store(tmp_path)
    work = Workbench(db, root, HybridSearch(db, root))
    def forbidden(*args, **kwargs):
        raise AssertionError('system count must not retrieve or infer')
    monkeypatch.setattr(work.search, 'search', forbidden)
    monkeypatch.setattr(work.generation, 'require', forbidden)
    run = work.create_answer('当前文献库中拥有多少篇文献', [], None, 'generative', 'hybrid')
    work.run_answer(run['id'])
    result = work.answers(run_id=run['id'])[0]
    assert result['status'] == 'completed' and not result['evidence'] and not result['model_history']
    assert result['result']['configuration']['document_count'] == 1
    project = Library(db).create_project('empty project')
    run = work.create_answer('当前文献库有多少篇文献', [], project['id'], 'generative', 'keyword')
    work.run_answer(run['id'])
    assert work.answers(project['id'], run_id=run['id'])[0]['result']['configuration']['document_count'] == 0
    with db.transaction() as conn:
        conn.execute("UPDATE document_versions SET visibility='hidden' WHERE id=?", (version,))
    run = work.create_answer('当前文献库有多少篇文献', [], None, 'extractive', 'keyword')
    work.run_answer(run['id'])
    assert work.answers(run_id=run['id'])[0]['result']['configuration']['document_count'] == 0
    assert system_information_topic('这篇文献使用了多少篇论文作为数据集') is None


@pytest.mark.parametrize('question,term', [
    ('该文献中主要的贡献是什么', 'bidirectional'),
    ('BERT这篇文献主要解决什么问题', 'unidirectional'),
])
def test_chinese_single_paper_overview_has_original_body_evidence(tmp_path, question, term):
    root, db, version = store(tmp_path)
    Parser(db, root).parse(version, 'parse')
    work = Workbench(db, root, HybridSearch(db, root))
    run = work.create_answer(question, [version], None, 'extractive', 'keyword')
    work.run_answer(run['id'])
    answer = work.answers(run_id=run['id'])[0]
    assert answer['status'] == 'completed'
    assert answer['result']['retrieval']['overview']['policy'] == 'bounded-document-sections-v2'
    assert 1 <= len(answer['evidence']) <= 3
    assert term in ' '.join(item['quote'].lower() for item in answer['evidence'])
    assert all(json.loads(item['anchor_json'])['page_number'] in {1, 2, 9} for item in answer['evidence'])
    for item in answer['evidence']:
        assert work.sources.anchor(item['source_anchor_id'])['doc_version_id'] == version
    assert section_candidates(db, [version, 'not-authorized'], None, overview_topic(question)) == []


def test_overview_section_lane_does_not_override_specific_questions():
    assert overview_topic('BERT的学习率是多少？') is None
    assert overview_topic('该文献中主要的贡献是什么') == 'contributions'
    assert overview_topic('What problem does this paper address?') == 'problem'


def test_ambiguous_single_paper_question_requires_explicit_selection(tmp_path):
    root, db, bert = store(tmp_path)
    other = PdfImporter(db, root).import_path_for_test(
        ROOT / 'tests/fixtures/public/2020.emnlp-main.550.pdf', 'dpr'
    )['doc_version_id']
    work = Workbench(db, root, HybridSearch(db, root))
    with pytest.raises(EngineError) as error:
        work.create_answer('该文献中主要的贡献是什么', [bert, other], None, 'extractive', 'keyword')
    assert error.value.code == 'DOCUMENT_SELECTION_REQUIRED'
    with db.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM answer_runs').fetchone()[0] == 0
