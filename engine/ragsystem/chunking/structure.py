"""Conservative page spans. Metadata never edits the source text or its offsets."""

import re

from ragsystem.chunking.mapping import chunk_page

CONFIG = {
    "strategy": "section_paragraph_v1",
    "max_chars": 400,
    "overlap_chars": 80,
    "sections": "conservative-headings-v2",
    "paragraphs": "blocks-blank-lines-v1",
    "fallback": "unclassified-paragraph-boundaries-v1",
    "short_merge": False,
}
NAMES = r"abstract|introduction|related work|background|method(?:s|ology)?|experiments?|results(?: and discussion)?|discussion|conclusions?|references|bibliography|appendix(?: [A-Z])?|摘要|绪论|引言|相关工作|研究方法|实验(?:与结果)?|结果|结论|参考文献|附录"
LABELS = {
    "title": "document_title",
    "document_title": "document_title",
    "abstract": "abstract",
    "appendix": "appendix",
    "section_header": "section_header",
    "text": "paragraph",
    "paragraph": "paragraph",
    "list_item": "list_item",
    "caption": "caption",
    "table": "table",
    "formula": "formula",
    "reference": "reference",
}


def heading(text, trusted=False):
    # Normalize only the title annotation. Source slices retain every character.
    value = " ".join(text.split())
    numbered = re.fullmatch(r"((?:\d+|[A-Z])(?:\.\d+){0,2})\.?\s+([^\n]{2,100})", value)
    name = numbered[2] if numbered else value
    known = bool(re.fullmatch(NAMES, name, re.I))
    # A numbered sentence/list is not enough evidence for a heading. Unknown
    # numbered titles require title case, no sentence punctuation, and 2+ words.
    title_case = bool(
        numbered
        and not re.match(r"^\d+\.\s", value)
        and len(name.split()) >= 2
        and all(
            w[0].isupper()
            or re.fullmatch(r"v\d+(?:\.\d+)*", w)
            or w.lower()
            in {"of", "and", "the", "for", "to", "in", "from", "with", "on", "at", "via", "as"}
            for w in name.split()
        )
    )
    acronym = bool(numbered and re.fullmatch(r"[A-Z][A-Z0-9-]{1,15}", name))
    # Appendix letters also occur in figures ("C T1", "O B-PER O").
    # A native letter-prefixed heading needs a prose title, not diagram labels.
    if numbered and numbered[1][0].isalpha() and not trusted and not re.search(r"[a-z]{3}", name):
        return None
    if (
        len(value) > 110
        or re.search(r"[。！？!?;；]", value)
        or (not trusted and re.search(r"[.:：]$", value))
    ):
        return None
    if not (
        trusted
        or known
        or title_case
        or acronym
        or (numbered and "." in numbered[1] and re.fullmatch(r"[\u4e00-\u9fff]{2,16}", name))
    ):
        return None
    level = len(numbered[1].split(".")) if numbered else 1
    kind = (
        "abstract"
        if re.fullmatch(r"abstract|摘要", name, re.I)
        else "reference"
        if re.fullmatch(r"references|bibliography|参考文献", name, re.I)
        else "appendix"
        if re.match(r"appendix|附录", name, re.I) or (numbered and numbered[1][0].isalpha())
        else "section_header"
    )
    return {
        "title": value,
        "level": level,
        "kind": kind,
        "number": numbered[1] if numbered else None,
        "method": "layout_label" if trusted else "text_pattern",
        "confidence": 0.9 if trusted else 0.65,
    }


def _native(text, offset=0):
    start = 0
    for line in re.finditer(r"[^\n]*(?:\n|$)", text):
        value = line[0].strip()
        special = heading(value)
        inline = re.match(r"^(Abstract|摘要)\s*[:：]", value, re.I)
        isolated = (
            not value
            or special
            or inline
            or re.match(r"^(?:(?:Figure|Fig\.|Table)\s*\d|图\s*\d|表\s*\d|[•●]|\[\d+\])", value)
        )
        if isolated:
            if text[start : line.start()].strip():
                yield {"start": offset + start, "end": offset + line.start(), "kind": "paragraph"}
            if value:
                if inline:
                    prefix = re.search(r"(?:Abstract|摘要)\s*[:：]", line[0], re.I)
                    split = line.start() + prefix.end()
                    yield {
                        "start": offset + line.start(),
                        "end": offset + split,
                        "kind": "abstract",
                        "heading": heading(inline[1]),
                    }
                    if text[split : line.end()].strip():
                        yield {
                            "start": offset + split,
                            "end": offset + line.end(),
                            "kind": "paragraph",
                        }
                else:
                    kind = (
                        special["kind"]
                        if special
                        else "list_item"
                        if value[0] in "•●"
                        else "reference"
                        if value.startswith("[")
                        else "caption"
                    )
                    yield {
                        "start": offset + line.start(),
                        "end": offset + line.end(),
                        "kind": kind,
                        "heading": special,
                    }
            start = line.end()
    if text[start:].strip():
        yield {"start": offset + start, "end": offset + len(text), "kind": "paragraph"}


def page_spans(text, blocks=None):
    """Consume validated serialized spans; uncovered text always remains available."""
    valid = sorted(
        (
            b
            for b in (blocks or [])
            if type(b.get("start")) is int
            and type(b.get("end")) is int
            and 0 <= b["start"] < b["end"] <= len(text)
        ),
        key=lambda b: b["start"],
    )
    cursor = 0
    for block in valid:
        if block["start"] < cursor:
            continue
        yield from _native(text[cursor : block["start"]], cursor)
        a, b = block["start"], block["end"]
        label = LABELS.get(block.get("label"), "unknown")
        title = heading(text[a:b], trusted=True) if label == "section_header" else None
        if text[a:b].strip():
            yield {
                "start": a,
                "end": b,
                "kind": title["kind"] if title else label,
                "heading": title,
            }
        cursor = b
    yield from _native(text[cursor:], cursor)


def structured_chunks(text, blocks=None):
    for span in page_spans(text, blocks):
        body = text[span["start"] : span["end"]]
        # Visual newlines remain inside the logical paragraph and exact slice.
        for chunk in chunk_page(
            body, max_chars=CONFIG["max_chars"], overlap=CONFIG["overlap_chars"], sentence_only=True
        ):
            yield {
                **chunk,
                "start": span["start"] + chunk["start"],
                "end": span["start"] + chunk["end"],
            }
