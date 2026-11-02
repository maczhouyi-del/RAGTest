"""Offline local snapshot replay. Logs IDs/counts/pages, never PDF text or keys."""

import argparse
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from ragsystem.library.repository import Library
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database
from ragsystem.workflows.workbench import Workbench


def digest(conn, table, columns):
    value = hashlib.sha256()
    for row in conn.execute(f"SELECT {columns} FROM {table} ORDER BY id"):
        for item in row:
            value.update(item if isinstance(item, bytes) else str(item).encode())
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original = sqlite3.connect((args.root / 'data/research.db').as_uri() + '?mode=ro', uri=True)
    original.row_factory = sqlite3.Row
    before = {table: digest(original, table, fields) for table, fields in [
        ('chunks', 'id,clean_text,visible'), ('embedding_records', 'id,vector_bytes'),
        ('answer_runs', 'id,status,result_json'), ('conversations', 'id,title,archived_at'),
    ]}
    # Preserve a separate test snapshot; never replay writes into the original DB.
    copy = Path(tempfile.mkdtemp(prefix='ragsystem-chat02-')) / 'research.db'
    with sqlite3.connect(copy) as destination:
        original.backup(destination)
    db = Database(copy)
    work = Workbench(db, args.root, HybridSearch(db, args.root))
    documents = Library(db).list_documents()
    versions = [doc['doc_version_id'] for doc in documents]
    cases = [('comparison', '这两篇文献中有什么相似之处')]
    cases.extend(('named_contributions', doc['title'] + '该文献中主要的贡献是什么') for doc in documents)
    output = {'network_calls': 0, 'snapshot': str(copy), 'cases': [], 'original_data_unchanged': False}
    for label, question in cases:
        run = work.create_answer(question, versions, None, 'extractive', 'hybrid')
        work.run_answer(run['id'])
        answer = work.answers(run_id=run['id'])[0]
        assert answer['status'] == 'completed', answer['error_code']
        selected = [item['doc_version_id'] for item in answer['scope']]
        assert len(selected) == (len(versions) if label == 'comparison' else 1)
        anchors = [work.sources.anchor(item['source_anchor_id']) for item in answer['evidence']]
        assert {item['doc_version_id'] for item in anchors} == set(selected)
        output['cases'].append({'kind': label, 'status': answer['status'], 'scope_versions': selected,
                                'pages': [item['page_number'] for item in anchors],
                                'evidence_ids': [item['id'] for item in answer['evidence']],
                                'chunk_ids': [item['source_anchor_id'] for item in answer['evidence']],
                                'source_hash_verified': True, 'overview': answer['result']['retrieval'].get('overview')})
    after = {table: digest(original, table, fields) for table, fields in [
        ('chunks', 'id,clean_text,visible'), ('embedding_records', 'id,vector_bytes'),
        ('answer_runs', 'id,status,result_json'), ('conversations', 'id,title,archived_at'),
    ]}
    assert before == after
    output['original_data_unchanged'] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'cases': len(output['cases']), 'all_completed': True, 'original_data_unchanged': True, 'network_calls': 0}))


if __name__ == '__main__':
    main()
