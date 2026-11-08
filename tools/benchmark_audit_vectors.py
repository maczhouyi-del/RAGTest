"""Isolated synthetic persistence/query comparison against the trusted audit baseline."""
import argparse
import json
import resource
import subprocess
import sys
import tempfile
import time
import tracemalloc
from contextlib import contextmanager
from pathlib import Path

from benchmark_audit_reads import BASELINE, baseline_class
from ragsystem.indexing.incremental import embed_visible
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.parsing.pipeline import Parser
from ragsystem.storage.database import Database
from ragsystem.vector_adapters.lancedb import LanceDB


class SyntheticEncoder:
    fingerprint = {
        'model': 'SYNTHETIC_NOT_A_MODEL', 'revision': '1', 'weight_sha256': 'a'*64,
        'tokenizer_sha256': 'b'*64, 'preprocessing': {}, 'dimension': 3,
        'metric': 'cosine', 'normalization': 'none',
    }

    def __init__(self):
        self.texts = 0

    def encode(self, texts):
        self.texts += len(texts)
        return [[1, 0, 0] for _ in texts]


def worker(mode, kind):
    with tempfile.TemporaryDirectory(prefix='ragsystem-audit-vectors-') as temporary:
        root = Path(temporary)
        if kind == 'persistence':
            db = Database(root/'data/research.db')
            fixture = Path(__file__).resolve().parents[1]/'tests/fixtures/public/N19-1423.pdf'
            version = PdfImporter(db, root).import_path_for_test(fixture, 'import')['doc_version_id']
            Parser(db, root).parse(version, 'parse')
            action = embed_visible
            if mode == 'baseline':
                # Helper loads only trusted local repository source, never document content.
                import types
                module = types.ModuleType('audit_old_incremental')
                source = subprocess.check_output(['git', 'show', BASELINE+':engine/ragsystem/indexing/incremental.py'])
                exec(compile(source, 'audit_old_incremental', 'exec'), module.__dict__)
                action = module.embed_visible
            transactions = []
            original = db.transaction
            @contextmanager
            def counted():
                transactions.append(1)
                with original() as conn:
                    yield conn
            db.transaction = counted
            encoder = SyntheticEncoder()
            start = time.perf_counter()
            first = action(db, encoder)
            elapsed = (time.perf_counter()-start)*1000
            first_transactions = len(transactions)
            transactions.clear()
            second = action(db, encoder)
            return {'first_ms':elapsed, 'new_vectors':first['new_embeddings'], 'encoded_texts':encoder.texts,
                    'transactions_first':first_transactions, 'transactions_reuse':len(transactions),
                    'reuse_new_vectors':second['new_embeddings']}
        cls = LanceDB if mode == 'current' else baseline_class('engine/ragsystem/vector_adapters/lancedb.py', 'LanceDB')
        adapter = cls(root/'lance', 'synthetic', 384)
        entries = [(f'id_{n:05}', [1.0] + [0.0]*383) for n in range(5000)]
        adapter.upsert(entries)
        eligible = {key for key, _ in entries if int(key[3:]) % 3}
        query = [1.0]+[0.0]*383
        tracemalloc.start()
        start = time.perf_counter()
        result = adapter.search_exact(query, eligible, 10)
        elapsed = (time.perf_counter()-start)*1000
        _, python_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert [r['embedding_id'] for r in result] == sorted(eligible)[:10]
        return {'elapsed_ms':elapsed, 'rows':5000, 'eligible':len(eligible), 'dimension':384,
                'returned':len(result), 'python_peak_bytes':python_peak,
                'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform=='darwin' else 1024)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=['baseline','current'])
    parser.add_argument('--kind', choices=['persistence','lance'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker, args.kind)))
        return
    report = {'baseline':BASELINE, 'scope':'synthetic vectors/public PDF engineering test; not model or thousand-paper validation', 'results':{}}
    for kind in ('persistence','lance'):
        report['results'][kind] = {}
        for mode in ('baseline','current'):
            result = subprocess.check_output([sys.executable, __file__, '--worker', mode, '--kind', kind], text=True)
            report['results'][kind][mode] = json.loads(result)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
