import hashlib

from ragsystem.chunking.mapping import chunk_page


def test_unicode_offsets_preserve_source_exactly():
    text = ("中文😀é\r\n实验条件与单位 25°C\n" * 100) + "结尾"
    chunks = list(chunk_page(text, max_chars=150))
    assert "".join(c["text"] for c in chunks) == text
    for chunk in chunks:
        assert text[chunk["start"] : chunk["end"]] == chunk["text"]
        assert chunk["content_sha256"] == hashlib.sha256(chunk["text"].encode()).hexdigest()
    assert list(chunk_page(" \r\n\t")) == []
