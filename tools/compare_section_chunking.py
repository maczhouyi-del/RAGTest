"""Isolated public-PDF A/B/C engineering comparison; never invents relevance gold."""

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from ragsystem.chunking.mapping import chunk_page
from ragsystem.chunking.publication import metadata
from ragsystem.chunking.structure import page_spans, structured_chunks
from ragsystem.ingestion.import_pdf import PdfImporter
from ragsystem.ipc.directories import Directories
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing import pipeline
from ragsystem.retrieval.hybrid import HybridSearch
from ragsystem.storage.database import Database


def paragraphs(text, blocks=None):
    for span in page_spans(text, blocks):
        body = text[span["start"] : span["end"]]
        yield {
            "start": span["start"],
            "end": span["end"],
            "text": body,
            "content_sha256": hashlib.sha256(body.encode()).hexdigest(),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = {
        "corpus": "two existing public fixtures; not user papers",
        "gold_metrics": "NOT EVALUATED: no independent span relevance or answer-support gold",
        "unscored_metrics": [
            "Recall@5",
            "MRR",
            "nDCG",
            "citation_accuracy",
            "answer_support",
        ],
        "parameters": {
            "k": 5,
            "strategy": "hybrid",
            "backend": "sqlite-vec",
            "reranking": False,
        },
        "arms": [],
    }
    for label, chunker in [
        ("A", lambda text, blocks=None: chunk_page(text)),
        ("B", paragraphs),
        ("C", structured_chunks),
    ]:
        root = Path(tempfile.mkdtemp(prefix="section-eval-" + label)).resolve()
        db = Database(root / "data/research.db")
        pipeline.structured_chunks = chunker
        pipeline.PARSER_CONFIG = {**pipeline.PARSER_CONFIG, "evaluation_arm": label}
        started = time.perf_counter()
        versions = []
        for sample in ["N19-1423.pdf", "2020.emnlp-main.550.pdf"]:
            v = PdfImporter(db, root).import_path_for_test(
                repo / "tests/fixtures/public" / sample, sample
            )["doc_version_id"]
            pipeline.Parser(db, root).parse(v, "parse-" + sample)
            versions.append(v)
        parse_seconds = time.perf_counter() - started
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT c.*,e.raw_text FROM chunks c JOIN elements e ON e.id=c.element_id WHERE c.visible=1"
            ).fetchall()
            aligned = sum(
                r["raw_text"][r["start_offset"] : r["end_offset"]] == r["clean_text"]
                for r in rows
            )
        search = HybridSearch(db, root)
        job = Jobs(db).enqueue("embed_batch", "index", {})
        started = time.perf_counter()
        search.build(
            job["id"],
            Directories().issue(args.model.resolve(), "embedding"),
            "sqlite-vec",
        )
        result = Jobs(db).get(job["id"])
        arm = {
            "arm": label,
            "root": str(root),
            "chunks": len(rows),
            "average_chars": sum(len(r["clean_text"]) for r in rows) / len(rows),
            "over_400": sum(len(r["clean_text"]) > 400 for r in rows),
            "parse_seconds": parse_seconds,
            "embedding_seconds": time.perf_counter() - started,
            "index_status": result["status"],
            "error_code": result.get("error_code"),
            "alignment_exact": aligned,
            "alignment_total": len(rows),
            "results": [],
        }
        if result["status"] == "completed":
            with db.connection() as conn:
                arm["embedding_fingerprint"] = json.loads(
                    conn.execute(
                        "SELECT fingerprint_json FROM embedding_spaces LIMIT 1"
                    ).fetchone()[0]
                )
            arm["embedding_counts"] = {
                k: search.config()[k] for k in ["new_embeddings", "reused_embeddings"]
            }
            for q in [
                "What is masked language modeling?",
                "How does dense passage retrieval work?",
            ]:
                hits = search.search(q, versions, 5, None, "hybrid")["results"]
                arm["results"].append(
                    {
                        "query": q,
                        "hits": [
                            {
                                "page": h["page_number"],
                                "chunk_id": h["chunk_id"],
                                "structure": h.get("structure"),
                                "anchor": search.sources.anchor(h["chunk_id"]),
                            }
                            for h in hits
                        ],
                    }
                )
            if label == "C":
                with db.connection() as conn:
                    example = conn.execute(
                        """SELECT c.*,p.start_offset AS paragraph_start,
                        p.end_offset AS paragraph_end FROM chunks c JOIN chunk_structure cs ON cs.chunk_id=c.id
                        JOIN document_paragraphs p ON p.id=cs.paragraph_id
                        JOIN document_sections s ON s.id=cs.section_id
                        WHERE c.doc_version_id=? AND s.section_title='3.1 Pre-training BERT'
                        AND p.end_offset-p.start_offset>400 ORDER BY c.start_offset LIMIT 1""",
                        (versions[0],),
                    ).fetchone()
                    if example is None:
                        raise RuntimeError("BERT_HIERARCHY_EXAMPLE_MISSING")
                    arm["real_example"] = {
                        **dict(example),
                        "structure": metadata(conn, example["id"]),
                        "embedding_ids": [
                            r[0]
                            for r in conn.execute(
                                "SELECT embedding_id FROM chunk_embedding_links WHERE chunk_id=?",
                                (example["id"],),
                            )
                        ],
                    }
                    unchanged = {
                        r[0]
                        for r in conn.execute(
                            "SELECT id FROM chunks WHERE visible=1 AND NOT (doc_version_id=? AND page_number=2)",
                            (versions[0],),
                        )
                    }
                arm["real_example"]["anchor"] = search.sources.anchor(example["id"])
                pipeline.Parser(db, root).parse(
                    versions[0], "partial-reuse", page_numbers=[2]
                )
                with db.connection() as conn:
                    current = {
                        r[0]
                        for r in conn.execute("SELECT id FROM chunks WHERE visible=1")
                    }
                    assert unchanged <= current
                rebuild = Jobs(db).enqueue("embed_batch", "rebuild-after-partial", {})
                search.build(
                    rebuild["id"],
                    Directories().issue(args.model.resolve(), "embedding"),
                    "sqlite-vec",
                )
                if Jobs(db).get(rebuild["id"])["status"] != "completed":
                    raise RuntimeError("PARTIAL_REBUILD_FAILED")
                arm["partial_rebuild"] = {
                    key: search.config()[key]
                    for key in ["new_embeddings", "reused_embeddings"]
                }
                assert arm["partial_rebuild"]["new_embeddings"] == 0
                arm["partial_rebuild"]["unselected_chunks_preserved"] = len(unchanged)
                arm["partial_rebuild"]["anchors_validated"] = sum(
                    bool(search.sources.anchor(cid)) for cid in current
                )
        output["arms"].append(arm)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            [
                {
                    k: v
                    for k, v in a.items()
                    if k
                    not in {"results", "root", "real_example", "embedding_fingerprint"}
                }
                for a in output["arms"]
            ],
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
