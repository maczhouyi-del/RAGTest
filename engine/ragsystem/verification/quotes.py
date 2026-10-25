from ragsystem.domain.errors import EngineError


def validate_quote(chunks, chunk_id, quote):
    if (
        not isinstance(chunk_id, str)
        or chunk_id not in chunks
        or not isinstance(quote, str)
        or not quote.strip()
        or len(quote) > 2000
    ):
        raise EngineError("MODEL_CITATION_INVALID")
    text = chunks[chunk_id]
    offset = text.find(quote)
    if offset < 0:
        raise EngineError("MODEL_CITATION_INVALID")
    return {"start": offset, "end": offset + len(quote)}
