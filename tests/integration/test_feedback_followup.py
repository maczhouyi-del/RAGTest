"""CHAT-02 engineering regression; public PDFs/fixtures, not scientific gold."""

import json

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.models.network_provider import NetworkProvider
from ragsystem.parsing.pipeline import Parser
from ragsystem.retrieval.document_overview import section_candidates
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.workflows.workbench import Workbench
from test_answer_pipeline import GeneratorFixture
from test_generation_providers import values
from test_mvp_core import ROOT, store


@pytest.fixture
def papers(tmp_path):
    root, db, one = store(tmp_path)
    two = PdfImporter(db, root).import_path_for_test(
        ROOT / 'tests/fixtures/public/2020.emnlp-main.550.pdf', 'dpr'
    )['doc_version_id']
    for version in (one, two):
        Parser(db, root).parse(version, 'parse-' + version)
    with db.transaction() as conn:
        conn.execute("UPDATE documents SET title='BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding' WHERE id=(SELECT document_id FROM document_versions WHERE id=?)", (one,))
        conn.execute("UPDATE documents SET title='Dense Passage Retrieval for Open-Domain Question Answering' WHERE id=(SELECT document_id FROM document_versions WHERE id=?)", (two,))
    return Workbench(db, root, HybridSearch(db, root)), one, two


def test_model_catalog_returns_all_ids_and_official_names(monkeypatch):
    provider = NetworkProvider({**values('https://api.deepseek.com/v1'), 'revision': 1}, 'fixture-key')
    monkeypatch.setattr(provider, 'request', lambda _: {'data': [
        {'id': 'deepseek-flash', 'name': 'Official Flash'},
        {'id': 'deepseek-v4-pro', 'name': 'Official Pro'},
        {'id': 'another-model'},
    ]})
    assert provider.models() == [
        {'id': 'deepseek-flash', 'name': 'Official Flash'},
        {'id': 'deepseek-v4-pro', 'name': 'Official Pro'},
        {'id': 'another-model', 'name': 'another-model'},
    ]
    provider.close()


@pytest.mark.parametrize('title', ['BERT', 'BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding'])
def test_explicit_title_resolves_only_within_selected_versions(papers, title):
    work, one, two = papers
    run = work.create_answer(title + '该文献中主要的贡献是什么', [one, two], None, 'extractive', 'keyword')
    assert [item['doc_version_id'] for item in work.answers(run_id=run['id'])[0]['scope']] == [one]
    with pytest.raises(EngineError, match='DOCUMENT_SELECTION_REQUIRED'):
        work.create_answer('该文献中主要的贡献是什么', [one, two], None, 'extractive', 'keyword')
    run = work.create_answer(title + '的主要贡献', [two], None, 'extractive', 'keyword')
    assert [item['doc_version_id'] for item in work.answers(run_id=run['id'])[0]['scope']] == [two]


def test_comparison_uses_body_from_both_papers_with_original_anchors(papers):
    work, one, two = papers
    run = work.create_answer('这两篇文献中有什么相似之处', [one, two], None, 'extractive', 'keyword')
    work.run_answer(run['id'])
    answer = work.answers(run_id=run['id'])[0]
    assert answer['status'] == 'completed'
    assert {json.loads(item['anchor_json'])['doc_version_id'] for item in answer['evidence']} == {one, two}
    assert len(answer['evidence']) <= 6
    assert all(json.loads(item['anchor_json'])['page_number'] <= 2 for item in answer['evidence'])
    assert 'bidirectional' in ' '.join(item['quote'].lower() for item in answer['evidence'])
    assert 'retrieval' in ' '.join(item['quote'].lower() for item in answer['evidence'])
    for item in answer['evidence']:
        assert work.sources.anchor(item['source_anchor_id'])['doc_version_id'] in {one, two}
        with work.db.connection() as conn:
            assert item['quote'] in conn.execute('SELECT clean_text FROM chunks WHERE id=?', (item['source_anchor_id'],)).fetchone()[0]


def test_inline_abstract_heading_and_small_chunk_continuation(papers):
    work, one, _ = papers
    # Explicit synthetic layout fixture exercises old 400-character chunks.
    with work.db.transaction() as conn:
        rows = conn.execute('SELECT id FROM chunks WHERE doc_version_id=? ORDER BY page_number,start_offset', (one,)).fetchall()
        conn.execute("UPDATE chunks SET visible=0 WHERE doc_version_id=?", (one,))
        texts = ['Authors and affiliations.\nAbstract: Wearable sensors monitor motor impairment.',
                 'We hypothesized that pre-training improves representations for motor impairment classification.',
                 'Results suggest higher classification accuracy using healthy adult motion data.',
                 'Keywords: sensor; model\n1. Introduction\nBackground.',
                 'References\nPrior cited work.']
        for index, text in enumerate(texts):
            conn.execute('UPDATE chunks SET clean_text=?,visible=1,page_number=1,start_offset=? WHERE id=?', (text, index * 200, rows[index]['id']))
    hits = section_candidates(work.db, [one], None, 'contributions')
    assert 'We hypothesized' in ' '.join(hit['preview'] for hit in hits[:3])
    assert 'Results suggest' in ' '.join(hit['preview'] for hit in hits[:3])
    assert not any('Prior cited work' in hit['preview'] for hit in hits)


@pytest.mark.parametrize('state,expected', [('empty', 'no_claims'), ('uncertain', 'unsupported_claims')])
def test_refusal_explains_empty_output_separately_from_support_check(papers, monkeypatch, state, expected):
    work, one, _ = papers
    generator = GeneratorFixture('uncertain')
    original = generator.generate
    def generate(task, data):
        result = original(task, data)
        if state == 'empty' and task == 'answer':
            result['claims'] = []
        return result
    monkeypatch.setattr(generator, 'generate', generate)
    monkeypatch.setattr(work.generation, 'require', lambda *args: generator)
    run = work.create_answer('BERT', [one], None, 'generative', 'keyword')
    work.run_answer(run['id'])
    answer = work.answers(run_id=run['id'])[0]
    assert answer['status'] == 'refused'
    assert answer['result']['refusal_detail']['reason'] == expected
    assert answer['result']['refusal_detail']['supported_claims'] == 0
    assert bool(answer['result']['support_checks']) == (state != 'empty')
