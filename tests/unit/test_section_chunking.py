import pytest
from ragsystem.chunking.structure import heading, page_spans, structured_chunks


@pytest.mark.parametrize(
    "title,level",
    [
        ("1 Introduction", 1),
        ("2.1 Research Background", 2),
        ("2.1.1 Model Architecture", 3),
        ("Abstract", 1),
        ("摘要", 1),
        ("1 绪论", 1),
        ("Methodology", 1),
        ("Experiments", 1),
        ("Results", 1),
        ("Conclusion", 1),
        ("References", 1),
        ("Appendix A", 1),
        ("参考文献", 1),
        ("3 BERT", 1),
        ("2.3 Transfer Learning from Supervised Data", 2),
        ("A Additional Details for BERT", 1),
        ("A.1 Training Details", 2),
        ("4.2 SQuAD v1.1", 2),
    ],
)
def test_headings(title, level):
    assert heading(title)["level"] == level


@pytest.mark.parametrize(
    "text",
    [
        "1. add the input.",
        "[1] Introduction",
        "Figure 1 Results",
        "We discuss Introduction in this paragraph.",
        "2024",
        "1. First, do this!",
        "Table 2 Experiments",
        "1. Install Software",
        "Tables are used for results.",
        "C T1",
        "O B-PER O",
    ],
)
def test_not_headings(text):
    assert heading(text) is None


@pytest.mark.parametrize(
    "body",
    [
        "短段😀é\n视觉换行。",
        "word " * 240,
        "中" * 1100,
        "line one\nline two\nline three",
        "OCR �" * 120,
    ],
)
def test_paragraph_offsets_and_overlap(body):
    text = "1 Introduction\n" + body + "\n\n2 Methods\nNext paragraph."
    chunks = list(structured_chunks(text))
    assert all(text[c["start"] : c["end"]] == c["text"] and len(c["text"]) <= 400 for c in chunks)
    spans = list(page_spans(text))
    for span in spans:
        within = [c for c in chunks if span["start"] <= c["start"] and c["end"] <= span["end"]]
        for a, b in zip(within, within[1:]):
            assert a["end"] - b["start"] == 80
    if len(body) < 350:
        assert any(body in c["text"] for c in chunks)
    assert not any("1 Introduction" in c["text"] and "Next paragraph" in c["text"] for c in chunks)


def test_layout_blocks_and_unresolved_gaps():
    text = "Methods\nBody\nformula\ncaption\n"
    blocks = [
        {"start": 0, "end": 7, "label": "section_header"},
        {"start": 13, "end": 20, "label": "formula"},
        {"start": 21, "end": 28, "label": "caption"},
        {"unresolved": True},
    ]
    spans = list(page_spans(text, blocks))
    assert [p["kind"] for p in spans] == [
        "section_header",
        "paragraph",
        "formula",
        "caption",
    ]
    assert list(structured_chunks(" \n\n\t")) == []


def test_context_metadata_is_not_part_of_quoted_text():
    from ragsystem.models.provider import numbered_excerpts

    chunk = {
        "chunk_id": "chunk",
        "text": "Exact source text.",
        "source": {
            "title": "Paper",
            "section_path": ["3 Methods", "3.1 Model"],
            "page_number": 4,
            "doc_version_id": "version",
        },
    }
    citations, excerpts = numbered_excerpts([chunk])
    assert excerpts[0]["quote"] == chunk["text"]
    assert excerpts[0]["source"]["section_path"] == chunk["source"]["section_path"]
    assert citations["E1"] == {"chunk_id": chunk["chunk_id"], "quote": chunk["text"]}


def test_wrapped_layout_heading_keeps_level_and_exact_source_slice():
    text = "3.1 Model\nArchitecture\n"
    blocks = [{"start": 0, "end": len(text), "label": "section_header"}]
    span = list(page_spans(text, blocks))[0]
    assert span["heading"]["level"] == 2
    assert span["heading"]["title"] == "3.1 Model Architecture"
    assert list(structured_chunks(text, blocks))[0]["text"] == text
