"""Opt-in candidate routing, with recorded engineering signals and guarded fallback."""

import unicodedata
from collections import defaultdict

from ragsystem.parsing.pdfium_words import words

POLICY = {
    "version": "quality-route-candidate-v1",
    "min_native_nonspace_chars": 24,
    "max_suspicious_ratio": 0.02,
    "min_preserved_ratio": 0.85,
    "max_enhanced_pages": 40,
    "geometry_sample_chars": 4000,
    "calibrated_against_scientific_gold": False,
}


def probe(page, textpage, text):
    native = "".join(text.split())
    suspicious = sum(c == "\ufffd" or unicodedata.category(c) in {"Co", "Cs", "Cc"} for c in native)
    tokens = words(textpage, sample_limit=POLICY["geometry_sample_chars"])
    width, _ = page.get_size()
    left_rows, right_rows = set(), set()
    numeric_rows = defaultdict(int)
    for token in tokens:
        left, b, r, t = token["bbox"]
        row = round((t + b) / 6)
        if 0.05 * width <= left <= 0.28 * width:
            left_rows.add(row)
        if 0.5 * width <= left <= 0.73 * width:
            right_rows.add(row)
        if any(c.isdigit() for c in token["text"]):
            numeric_rows[row] += 1
    return {
        "nonspace_chars": len(native),
        "suspicious_ratio": suspicious / max(1, len(native)),
        "multi_column_candidate": len(left_rows) >= 5 and len(right_rows) >= 5,
        "numeric_grid_candidate": sum(n >= 3 for n in numeric_rows.values()) >= 3,
        "geometry_sample_chars": min(textpage.count_chars(), POLICY["geometry_sample_chars"]),
    }


def choose(pages, *, ocr_available, docling_available):
    decisions = []
    budgets = {"ocr": 0, "docling": 0}
    for page in pages:
        s = page.get("signals", {})
        if page["error_code"]:
            method, reason = "native_text", "NATIVE_PAGE_FAILED"
        elif (
            s.get("nonspace_chars", len(page["text"].strip())) < POLICY["min_native_nonspace_chars"]
        ):
            method, reason = "ocr", "LOW_NATIVE_TEXT"
        elif s.get("suspicious_ratio", 0) >= POLICY["max_suspicious_ratio"]:
            method, reason = "ocr", "SUSPICIOUS_NATIVE_TEXT"
        elif s.get("multi_column_candidate") or s.get("numeric_grid_candidate"):
            method, reason = "docling", "LAYOUT_COMPLEXITY_CANDIDATE"
        else:
            method, reason = "native_text", "NATIVE_TEXT_CANDIDATE"
        desired = method
        if method != "native_text":
            available = ocr_available if method == "ocr" else docling_available
            if not available:
                method, reason = "native_text", "RESOURCE_NOT_CONFIGURED:" + reason
            elif budgets[method] >= POLICY["max_enhanced_pages"]:
                method, reason = "native_text", "ENHANCEMENT_PAGE_BUDGET"
            else:
                budgets[method] += 1
        decisions.append(
            {
                "page_number": page["page_number"],
                "method": method,
                "desired_method": desired,
                "reason": reason,
                "signals": s,
            }
        )
    return decisions


def accept(native, enhanced):
    if enhanced.get("error_code") or not enhanced["text"].strip():
        return False, "ENHANCEMENT_INCOMPLETE"
    if enhanced.get("method") == "ocr":
        if (enhanced.get("mean_confidence") or 0) < 60:
            return False, "OCR_LOW_CONFIDENCE"
    elif (
        len("".join(enhanced["text"].split()))
        < len("".join(native["text"].split())) * POLICY["min_preserved_ratio"]
    ):
        return False, "TEXT_COVERAGE_DECREASED"
    return True, "CANDIDATE_ACCEPTED_UNREVIEWED"
