"""Expansion Feature 6 unit tests: the deterministic machinery —
extractors (real per-format extraction, honest failures), the
locator-preserving chunker, and the labelled file-intelligence
statistics. No application is booted here.
"""
from __future__ import annotations

import pytest

from app.knowledge import extractors
from app.knowledge.chunking import (
    chunk_segments, extractive_excerpt, keyphrases,
)
from app.knowledge.extractors import Segment
from app.knowledge.service import _slugify
from tests.f06_support import (
    CSV_BYTES, TXT_BYTES, make_docx_bytes, make_pdf_bytes,
    make_png_bytes, make_pptx_bytes, make_xlsx_bytes,
)


# ------------------------------------------------------------ extractors
def test_text_extraction_locates_line_ranges():
    segments, detail = extractors.extract("text", TXT_BYTES)
    assert detail["lines"] == 3
    assert segments[0].locator == "lines 1–3"
    assert "budget review" in segments[0].text


def test_csv_extraction_carries_header_and_row_locators():
    segments, detail = extractors.extract("csv", CSV_BYTES)
    assert detail["columns"] == ["item", "amount"]
    assert detail["rows"] == 3
    assert segments[0].locator.startswith("rows 2–")
    assert segments[0].text.startswith("item, amount")


def test_pdf_extraction_is_real_and_page_located():
    data = make_pdf_bytes(["Alpha page one content.",
                           "Beta page two content."])
    segments, detail = extractors.extract("pdf", data)
    assert detail == {"pages": 2}
    assert [s.locator for s in segments] == ["page 1", "page 2"]
    assert segments[0].text == "Alpha page one content."
    assert segments[1].text == "Beta page two content."


def test_docx_extraction_covers_paragraphs_and_tables():
    segments, detail = extractors.extract("docx", make_docx_bytes())
    assert detail["paragraphs"] == 2
    assert detail["tables"] == 1
    joined = "\n".join(s.text for s in segments)
    assert "kickoff notes" in joined
    assert "Owner | Milestone" in joined
    assert any(s.locator == "table 1" for s in segments)


def test_xlsx_extraction_is_sheet_and_row_located():
    segments, detail = extractors.extract("xlsx", make_xlsx_bytes())
    assert detail["sheets"] == {"Budget": 3, "Notes": 1}
    budget = [s for s in segments if "Budget" in s.locator]
    assert budget and "Hosting | 120" in budget[0].text


def test_pptx_extraction_is_slide_located():
    segments, detail = extractors.extract("pptx", make_pptx_bytes())
    assert detail == {"slides": 2}
    assert segments[0].locator == "slide 1"
    assert "roadmap" in segments[0].text


def test_image_extraction_is_metadata_only_ocr_not_implemented():
    segments, detail = extractors.extract("image", make_png_bytes())
    assert segments == []  # no text returned, none invented
    assert detail["image_format"] == "PNG"
    assert detail["ocr"] == "not_implemented"


def test_malformed_pdf_fails_extraction_honestly():
    with pytest.raises(extractors.ExtractionError):
        extractors.extract("pdf", b"%PDF- not a real pdf at all")


def test_malformed_docx_fails_extraction_honestly():
    with pytest.raises(extractors.ExtractionError):
        extractors.extract("docx", b"PK\x03\x04 garbage")


def test_unsupported_format_raises():
    with pytest.raises(extractors.UnsupportedFormat):
        extractors.extract("rtf", b"{\\rtf1 hello}")


def test_format_support_is_probed_and_honest():
    support = extractors.format_support()
    assert support["pdf"] == "supported"
    assert support["docx"] == "supported"
    assert support["image"] == "metadata_only_ocr_not_implemented"
    assert support["ocr"] == "not_implemented"


# -------------------------------------------------------------- chunking
def test_chunker_never_crosses_a_locator_boundary():
    segments = [Segment("page 1", "alpha " * 200),
                Segment("page 2", "beta " * 200)]
    chunks = chunk_segments(segments)
    assert chunks
    for chunk in chunks:
        assert chunk.locator in ("page 1", "page 2")
        body = chunk.text
        assert not ("alpha" in body and "beta" in body)


def test_chunker_respects_hard_cap_and_char_offsets():
    segments = [Segment("page 1", "x" * 5000)]
    chunks = chunk_segments(segments)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert len(chunk.text) <= 2000
        assert chunk.char_end - chunk.char_start == len(chunk.text)
    assert chunks[0].char_start == 0
    assert chunks[1].char_start > chunks[0].char_start


def test_chunker_offsets_span_segments_with_join_newline():
    segments = [Segment("lines 1–1", "abc"), Segment("lines 2–2", "def")]
    chunks = chunk_segments(segments)
    assert len(chunks) == 2
    assert chunks[1].char_start == 4  # "abc" + the joining "\n"


# ------------------------------------------------------------ intelligence
def test_keyphrases_are_frequency_statistics():
    phrases = keyphrases("budget budget budget review review plan")
    assert phrases[0] == {"phrase": "budget", "count": 3}
    assert all(set(p) == {"phrase", "count"} for p in phrases)


def test_excerpt_is_verbatim_and_labelled_extract():
    text = ("The hosting bill arrived on Tuesday. "
            "The budget review approved new hosting spend. "
            "Lunch was sandwiches.")
    result = extractive_excerpt(text, "hosting budget", sentences=1)
    assert result["method"] == "deterministic_extract"
    assert "not an AI summary" in result["label"]
    assert result["sentences"] == [
        "The budget review approved new hosting spend."]


def test_slugify_is_stable():
    assert _slugify("Aurora Project!") == "aurora-project"
    assert _slugify("") == "collection"
    assert _slugify("  Spaces  Everywhere ") == "spaces-everywhere"
