import hashlib
import re


def chunk_page(text: str, max_chars=400, *, overlap=None):
    """Keep exact Unicode code-point offsets; no lossy text cleaning or fake bbox."""
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    overlap = min(80, max_chars // 5) if overlap is None else overlap
    if type(overlap) is not int or not 0 <= overlap < max_chars // 2:
        raise ValueError("invalid overlap")
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundaries = list(
                re.finditer(r"\n|[。！？；]|[.!?](?=\s|$)", text[start + max_chars // 2 : end])
            )
            if boundaries:
                end = start + max_chars // 2 + boundaries[-1].end()
        content = text[start:end]
        if content.strip():
            yield {
                "start": start,
                "end": end,
                "text": content,
                "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
            }
        if end == len(text):
            break
        start = end - overlap
