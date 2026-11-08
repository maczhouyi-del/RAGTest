from ragsystem.indexing.embeddings import Embeddings
from ragsystem.storage.database import Database


def embed_visible(db: Database, encoder, *, batch_size=8, progress=lambda current, total: None):
    if not 1 <= batch_size <= 16:
        raise ValueError("invalid batch size")
    cache = Embeddings(db)
    space = cache.space(encoder.fingerprint)
    with db.connection() as conn:
        chunks = conn.execute("""SELECT c.* FROM chunks c JOIN document_versions v ON v.id=c.doc_version_id
            WHERE c.visible=1 AND v.visibility='visible' ORDER BY c.id""").fetchall()
    grouped = {}
    for chunk in chunks:
        entry = grouped.setdefault(
            chunk["content_sha256"], {"text": chunk["clean_text"], "chunks": []}
        )
        entry["chunks"].append(chunk["id"])
    missing, reused, links = [], 0, []

    def flush_links():
        progress(reused, len(grouped))
        with db.transaction() as conn:
            for chunk_id, record_id in links:
                cache.link(chunk_id, record_id, connection=conn)
        links.clear()

    entries = list(grouped.items())
    for start in range(0, len(entries), 128):
        progress(reused, len(grouped))
        batch = entries[start : start + 128]
        records = cache.get_many(space, [digest for digest, _ in batch])
        for digest, entry in batch:
            record = records.get(digest)
            if record:
                for chunk_id in entry["chunks"]:
                    links.append((chunk_id, record["id"]))
                    if len(links) == 128:
                        flush_links()
                reused += 1
            else:
                missing.append((digest, entry))
    if links:
        flush_links()
    for start in range(0, len(missing), batch_size):
        progress(reused + start, len(grouped))
        batch = missing[start : start + batch_size]
        vectors = encoder.encode([entry["text"] for _, entry in batch])
        if len(vectors) != len(batch):
            raise ValueError("embedding batch size mismatch")
        # Inference is outside the short write transaction; recheck cancellation
        # before persisting. Each batch is atomic, and no index is published here.
        progress(reused + start, len(grouped))
        with db.transaction() as conn:
            for (digest, _entry), vector in zip(batch, vectors, strict=True):
                cache.persist(space, digest, vector, connection=conn)
        # Link in bounded transactions even when one shared text occurs in many chunks.
        records = cache.get_many(space, [digest for digest, _ in batch])
        for digest, entry in batch:
            for chunk_id in entry["chunks"]:
                links.append((chunk_id, records[digest]["id"]))
                if len(links) == 128:
                    flush_links()
    if links:
        flush_links()
    return {
        "space_id": space,
        "chunks": len(chunks),
        "new_embeddings": len(missing),
        "reused_embeddings": reused,
    }
