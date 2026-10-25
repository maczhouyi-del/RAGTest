"""Native glyph-derived word candidates; no inferred scientific cell boundaries."""

import math

import pypdfium2.raw as raw

from ragsystem.domain.errors import EngineError

VERSION = "pdfium-glyph-words-v1"


def words(textpage, *, limit=50000, sample_limit=None):
    count = textpage.count_chars()
    if count > limit:
        raise EngineError("PAGE_TEXT_LIMIT")
    result, units, bounds = [], [], None

    def flush():
        nonlocal units, bounds
        if units and bounds:
            text = (
                "".join(units).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
            )
            result.append({"text": text, "bbox": bounds})
        units, bounds = [], None

    for index in range(min(count, sample_limit) if sample_limit else count):
        code = raw.FPDFText_GetUnicode(textpage.raw, index)
        char = chr(code) if 0 < code <= 0x10FFFF else "\ufffd"
        if char.isspace() or code == 0:
            flush()
            continue
        box = tuple(textpage.get_charbox(index))  # unrotated PDF coordinates
        left, b, r, t = box
        if not all(math.isfinite(v) for v in box) or r <= left or t <= b:
            flush()
            continue
        if bounds:
            pl, pb, pr, pt = bounds
            height = max(t - b, pt - pb)
            # Baseline changes, reverse runs and a large horizontal gap cannot
            # be merged across a table column. This is versioned preprocessing.
            if (
                abs((t + b) - (pt + pb)) > height
                or left - pr > height * 0.45
                or left < pl - height * 0.2
            ):
                flush()
        units.append(char)
        bounds = (
            (min(bounds[0], left), min(bounds[1], b), max(bounds[2], r), max(bounds[3], t))
            if bounds
            else box
        )
    flush()
    return result
