import os
from pathlib import Path

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.models.local_onnx import LocalE5
from ragsystem.workflows.workbench import Workbench


@pytest.fixture(scope='module')
def encoder():
    directory = os.environ.get('RAGSYSTEM_MODEL_DIR')
    if not directory:
        pytest.skip('Explicit approved locked E5 resource required')
    return LocalE5(Path(directory))


def exact_text(encoder, count, query):
    from tokenizers import Tokenizer
    counter = Tokenizer.from_str(encoder.tokenizer.to_str())
    counter.no_truncation()
    counter.no_padding()
    prefix = 'query: ' if query else 'passage: '
    for n in range(count - 16, count + 1):
        text = 'cat '*n
        if len(counter.encode(prefix + text).ids) == count:
            return text
    raise AssertionError('Boundary fixture cannot be constructed with locked tokenizer')


@pytest.mark.parametrize('query', [True, False])
@pytest.mark.parametrize('tokens', [511, 512, 513])
def test_real_token_boundaries_and_distinct_errors(encoder, query, tokens):
    text = exact_text(encoder, tokens, query)
    before = encoder.calls
    if tokens > 512:
        code = 'QUERY_CONTEXT_LIMIT' if query else 'EMBEDDING_CONTEXT_LIMIT'
        with pytest.raises(EngineError, match=code):
            encoder.encode([text], query=query)
        assert encoder.calls == before
    else:
        assert len(encoder.encode([text], query=query)[0]) == 384


def test_current_question_kept_history_dropped_and_audited(encoder):
    question = 'Does it work? ' + exact_text(encoder, 450, True)
    history = [{'question': 'old topic '*180}, {'question': 'recent topic '*180}]
    selected, policy = Workbench.retrieval_context(question, history, query_fits=encoder.query_fits)
    assert selected == [] and policy['retrieval_query'] == question
    assert policy['dropped_history_turns'] == 2 and policy['query_token_limit'] == 512
    with pytest.raises(EngineError, match='QUERY_CONTEXT_LIMIT'):
        Workbench.retrieval_context(exact_text(encoder, 513, True), history, query_fits=encoder.query_fits)


def test_query_overflow_does_not_change_published_index(tmp_path, encoder):
    from ragsystem.ingestion.import_pdf import PdfImporter
    from ragsystem.ipc.directories import Directories
    from ragsystem.jobs.repository import Jobs
    from ragsystem.parsing.pipeline import Parser
    from ragsystem.retrieval.hybrid import HybridSearch
    from ragsystem.storage.database import Database
    db = Database(tmp_path/'data/research.db')
    fixture = Path(__file__).resolve().parents[1]/'fixtures/public/N19-1423.pdf'
    version = PdfImporter(db, tmp_path).import_path_for_test(fixture, 'import')['doc_version_id']
    Parser(db, tmp_path).parse(version, 'parse')
    search = HybridSearch(db, tmp_path)
    job = Jobs(db).enqueue('embed_batch', 'index', {})
    directory = Directories().issue(Path(os.environ['RAGSYSTEM_MODEL_DIR']), 'embedding')
    search.build(job['id'], directory, 'sqlite-vec')
    assert Jobs(db).get(job['id'])['status'] == 'completed'
    before = search.config()
    with pytest.raises(EngineError, match='QUERY_CONTEXT_LIMIT'):
        search.search(exact_text(encoder, 513, True), [version], 5, None, 'hybrid')
    assert search.config() == before and search.status()['ready']
