"""Real native glyph grouping; no assertion about scientific bbox calibration."""

import math
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium
from ragsystem.parsing.pdfium_words import words


def test_real_table_page_supplies_distinct_glyph_words_with_finite_boxes():
    path = Path(__file__).resolve().parents[2] / "tests/fixtures/public/N19-1423.pdf"
    with (
        pdfium.PdfDocument(path) as doc,
        closing(doc[6]) as page,
        closing(page.get_textpage()) as text,
    ):
        tokens = words(text)
        assert len(tokens) > 300
        assert sum(any(c.isdigit() for c in t["text"]) for t in tokens) > 40
        assert all(len(t["bbox"]) == 4 and all(math.isfinite(v) for v in t["bbox"]) for t in tokens)
        assert all(not any(c.isspace() for c in t["text"]) for t in tokens)
        sample = words(text, sample_limit=40)
        assert len(sample) <= len(tokens)
