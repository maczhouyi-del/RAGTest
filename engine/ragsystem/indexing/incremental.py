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
    missing, reused = [], 0
    for digest, entry in grouped.items():
        progress(reused, len(grouped))
        record = cache.get(space, digest)
        if record:
            for chunk_id in entry["chunks"]:
                cache.link(chunk_id, record["id"])
            reused += 1
        else:
            missing.append((digest, entry))
    for start in range(0, len(missing), batch_size):
        progress(reused + start, len(grouped))
        batch = missing[start : start + batch_size]
        vectors = encoder.encode([entry["text"] for _, entry in batch])
        if len(vectors) != len(batch):
            raise ValueError("embedding batch size mismatch")
        for (digest, entry), vector in zip(batch, vectors, strict=True):
            record_id = cache.persist(space, digest, vector)
            for chunk_id in entry["chunks"]:
                cache.link(chunk_id, record_id)
    return {
        "space_id": space,
        "chunks": len(chunks),
        "new_embeddings": len(missing),
        "reused_embeddings": reused,
    }
