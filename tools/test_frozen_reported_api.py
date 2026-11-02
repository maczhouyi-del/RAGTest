"""Explicit user-authorized frozen API check; only hash-verified public BERT excerpts.

Never run in CI. Secret is read without echo, kept in memory, and redacted from
output. Source DB is read-only; all operations run in a new isolated copy.
"""

import argparse
import getpass
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / 'tests/integration'))
    import httpx
    from test_sidecar_lifecycle import start_sidecar, stop_sidecar

    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    base = repo / '.tools/test-data' / ('rag03-frozen-' + str(uuid4()))
    root = base / '中文 空格'
    (root / 'data').mkdir(parents=True)
    public_sha = hashlib.sha256((repo / 'tests/fixtures/public/N19-1423.pdf').read_bytes()).hexdigest()
    assert public_sha == '987545ffb087f1ece898142c403a516baeabeb70ce19089397fac6f7db12c3d4'
    source = sqlite3.connect((args.source_root / 'data/research.db').resolve().as_uri() + '?mode=ro', uri=True)
    destination = sqlite3.connect(root / 'data/research.db')
    source.backup(destination)
    source.close()
    version = destination.execute('select id from document_versions where file_sha256=?', (public_sha,)).fetchone()[0]
    expected_count = destination.execute("select count(distinct document_id) from document_versions where visibility='visible'").fetchone()[0]
    config = json.loads(destination.execute("select value_json from app_settings where key='active_index'").fetchone()[0])
    destination.close()
    (root / 'papers').mkdir()
    shutil.copy2(repo / 'tests/fixtures/public/N19-1423.pdf', root / 'papers' / (public_sha + '.pdf'))
    index = Path(config['relative_path'])
    assert not index.is_absolute() and '..' not in index.parts
    (root / index).parent.mkdir(parents=True)
    shutil.copy2(args.source_root / index, root / index)
    secret = getpass.getpass('DeepSeek Key (memory only): ')
    record = {'started_at': stamp, 'root': str(root), 'binary_sha256': hashlib.sha256(args.binary.read_bytes()).hexdigest(),
              'only_external_source_sha256': public_sha, 'maximum_generation_POSTs': 6, 'answers': [], 'status': 'FAIL'}
    process = client = None
    try:
        process, client, token = start_sidecar(base, [str(args.binary.resolve())])
        base_url = str(client.base_url)
        client.close()
        # Match Rust's fresh-loopback-connection policy (sidecar keep-alive is 2s).
        client = httpx.Client(base_url=base_url, headers={'X-RAG-Session': token},
                             trust_env=False, timeout=70,
                             limits=httpx.Limits(max_keepalive_connections=0))
        def call(method, path, body=None):
            response = client.request(method, path, json=body)
            value = response.json()
            if response.status_code >= 400:
                raise RuntimeError(value.get('code', 'IPC_REQUEST_FAILED'))
            return value
        record['health'] = call('GET', '/v0/health')
        assert record['health']['build']['label'] == 'RAG-03'
        preview = call('POST', '/v0/generation-provider-probe', {
            'kind':'api', 'base_url':'https://api.deepseek.com/v1', 'auth_mode':'bearer', 'api_key':secret})
        assert any(row['id']=='deepseek-flash' for row in preview['models'])
        saved = call('POST', '/v0/generation-providers', {
            'id':None, 'expected_revision':0, 'name':'RAG-03 public BERT test',
            'kind':'api', 'vendor':'deepseek', 'base_url':'https://api.deepseek.com/v1',
            'model':'deepseek-flash', 'credential_token':preview['credential_token'], 'enable_for_documents':True})
        conversation = None
        for question, strategy in [('当前文献库中拥有多少篇文献','hybrid'),
                                   ('该文献中主要的贡献是什么','keyword'),
                                   ('BERT这篇文献主要解决什么问题','hybrid')]:
            run = call('POST','/v0/answers', {
                'question':question, 'version_ids':[version], 'project_id':None, 'mode':'generative',
                'strategy':strategy, 'conversation_id':conversation, 'provider_id':saved['id'],
                'provider_revision':saved['revision'], 'per_paper_limit':3})
            conversation = run['conversation_id']
            deadline = time.monotonic() + 210
            while True:
                answer = call('GET', '/v0/answers/' + run['id'])
                if answer['status'] not in {'queued','running'}:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('TEST_DEADLINE_EXCEEDED')
                time.sleep(0.25)
            record['answers'].append(answer)
            print(json.dumps({'question':question,'status':answer['status'],'code':answer['error_code']},ensure_ascii=False),flush=True)
            assert answer['status']=='completed', answer['error_code']
            if len(record['answers'])==1:
                assert answer['result']['configuration']['document_count']==expected_count
                assert not answer['evidence'] and not answer['model_history']
            else:
                assert answer['claims'] and all(c['model_support']=='supported' for c in answer['claims'])
                assert all(json.loads(e['anchor_json'])['doc_version_id']==version for e in answer['evidence'])
        record['status']='PASS'
    except Exception as exc:
        record['error_type']=type(exc).__name__
        record['error']=str(exc).replace(secret,'[REDACTED]')[:300]
    finally:
        if client:
            client.close()
        if process:
            stop_sidecar(process)
        encoded=json.dumps(record,ensure_ascii=False,indent=2)
        assert secret not in encoded
        with sqlite3.connect(root/'data/research.db') as check:
            assert secret not in '\n'.join(check.iterdump())
        target=repo/'docs/engineering/evidence/RAG-03'/('frozen-real-api-'+stamp+'.json')
        target.write_text(encoded+'\n')
        print(json.dumps({'status':record['status'],'record':str(target),'error':record.get('error')},ensure_ascii=False))
    return 0 if record['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
