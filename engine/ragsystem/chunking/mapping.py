import hashlib


def chunk_page(text: str, max_chars=1200):
    """Keep exact Unicode code-point offsets; no lossy text cleaning or fake bbox."""
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + max_chars // 2, end)
            if boundary > start:
                end = boundary + 1
        content = text[start:end]
        if content.strip():
            yield {
                "start": start,
                "end": end,
                "text": content,
                "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
            }
        start = end
