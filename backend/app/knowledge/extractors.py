"""Document extraction for F06 — REAL extraction per format, or
an honest refusal. No extractor invents text:

- text / markdown / code: UTF-8 decode (replacement chars noted),
  located by line range (stdlib).
- csv: parsed rows, located by row range, header carried into
  every segment (stdlib).
- pdf: ``pypdf`` per-page text, located by page.
- docx: ``python-docx`` paragraphs and tables in body order,
  located by paragraph range / table number.
- xlsx: ``openpyxl`` per sheet, located by sheet + row range.
- pptx: ``python-pptx`` per slide, located by slide.
- image: ``Pillow`` metadata only. **OCR is NOT IMPLEMENTED** —
  no OCR engine exists in this environment (no tesseract
  binary); image text is never guessed.

A file whose bytes do not parse as its claimed format raises
:class:`ExtractionError` and the document is recorded
``extraction_failed`` — never silently re-interpreted as another
format. All libraries are local; nothing here touches a network.
"""
from __future__ import annotations

import csv
import io
from typing import NamedTuple


class UnsupportedFormat(Exception):
    """No extractor exists for this format."""


class ExtractionError(Exception):
    """The real parser refused these bytes."""


class Segment(NamedTuple):
    locator: str
    text: str


def format_support() -> dict:
    """Runtime-probed per-format support states — reported, never
    asserted from a list alone."""
    support = {"text": "supported", "markdown": "supported",
               "code": "supported", "csv": "supported"}
    for fmt, module in (("pdf", "pypdf"), ("docx", "docx"),
                        ("xlsx", "openpyxl"), ("pptx", "pptx")):
        try:
            __import__(module)
            support[fmt] = "supported"
        except Exception:
            support[fmt] = "not_configured"
    support["image"] = "metadata_only_ocr_not_implemented"
    support["ocr"] = "not_implemented"
    return support


def extractor_name(fmt: str) -> str:
    return {
        "text": "stdlib-utf8", "markdown": "stdlib-utf8",
        "code": "stdlib-utf8", "csv": "stdlib-csv",
        "pdf": "pypdf", "docx": "python-docx",
        "xlsx": "openpyxl", "pptx": "python-pptx",
        "image": "pillow-metadata",
    }.get(fmt, "none")


def extract(fmt: str, data: bytes) -> tuple[list[Segment], dict]:
    handler = _HANDLERS.get(fmt)
    if handler is None:
        raise UnsupportedFormat(f"no extractor for format '{fmt}'")
    return handler(data)


# ---------------------------------------------------------------- text
def _extract_text(data: bytes) -> tuple[list[Segment], dict]:
    replaced = False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        replaced = True
    lines = text.splitlines()
    segments: list[Segment] = []
    block = 40
    for start in range(0, len(lines), block):
        part = lines[start:start + block]
        segments.append(Segment(
            locator=f"lines {start + 1}–{start + len(part)}",
            text="\n".join(part)))
    if not segments:
        segments = []
    return segments, {"lines": len(lines),
                      "decode_replacements": replaced}


def _extract_csv(data: bytes) -> tuple[list[Segment], dict]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    try:
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
    except csv.Error as exc:
        raise ExtractionError(f"csv parse failed: {exc}") from exc
    if not rows:
        return [], {"rows": 0, "columns": []}
    header, body = rows[0], rows[1:]
    segments: list[Segment] = []
    block = 25
    for start in range(0, len(body), block):
        part = body[start:start + block]
        lines = [", ".join(header)] + [", ".join(r) for r in part]
        segments.append(Segment(
            locator=f"rows {start + 2}–{start + 1 + len(part)}",
            text="\n".join(lines)))
    if not body:
        segments = [Segment(locator="row 1 (header)",
                            text=", ".join(header))]
    return segments, {"rows": len(body), "columns": header}


# ----------------------------------------------------------------- pdf
def _extract_pdf(data: bytes) -> tuple[list[Segment], dict]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractionError("pypdf is not installed") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError("pdf is encrypted; text not extracted")
        segments = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            segments.append(Segment(locator=f"page {index + 1}", text=text))
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"pdf parse failed: {exc}") from exc
    return segments, {"pages": len(segments)}


# ---------------------------------------------------------------- docx
def _extract_docx(data: bytes) -> tuple[list[Segment], dict]:
    try:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise ExtractionError("python-docx is not installed") from exc
    try:
        document = docx.Document(io.BytesIO(data))
        paragraphs: list[str] = []
        tables: list[list[list[str]]] = []
        for child in document.element.body.iterchildren():
            if child.tag.endswith("}p"):
                paragraphs.append(Paragraph(child, document).text)
            elif child.tag.endswith("}tbl"):
                table = Table(child, document)
                tables.append([[cell.text for cell in row.cells]
                               for row in table.rows])
    except Exception as exc:
        raise ExtractionError(f"docx parse failed: {exc}") from exc
    segments: list[Segment] = []
    block = 30
    for start in range(0, len(paragraphs), block):
        part = paragraphs[start:start + block]
        segments.append(Segment(
            locator=f"paragraphs {start + 1}–{start + len(part)}",
            text="\n".join(part)))
    for number, table in enumerate(tables, start=1):
        text = "\n".join(" | ".join(row) for row in table)
        segments.append(Segment(locator=f"table {number}", text=text))
    return segments, {"paragraphs": len(paragraphs),
                      "tables": len(tables)}


# ---------------------------------------------------------------- xlsx
def _extract_xlsx(data: bytes) -> tuple[list[Segment], dict]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ExtractionError("openpyxl is not installed") from exc
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True,
                                 data_only=True)
        segments: list[Segment] = []
        sheet_rows: dict[str, int] = {}
        block = 25
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                cells = ["" if c is None else str(c) for c in row]
                if any(c.strip() for c in cells):
                    rows.append(" | ".join(cells))
            sheet_rows[sheet.title] = len(rows)
            for start in range(0, len(rows), block):
                part = rows[start:start + block]
                segments.append(Segment(
                    locator=(f"sheet '{sheet.title}' "
                             f"rows {start + 1}–{start + len(part)}"),
                    text="\n".join(part)))
        workbook.close()
    except Exception as exc:
        raise ExtractionError(f"xlsx parse failed: {exc}") from exc
    return segments, {"sheets": sheet_rows}


# ---------------------------------------------------------------- pptx
def _extract_pptx(data: bytes) -> tuple[list[Segment], dict]:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise ExtractionError("python-pptx is not installed") from exc
    try:
        presentation = Presentation(io.BytesIO(data))
        segments: list[Segment] = []
        for index, slide in enumerate(presentation.slides):
            parts: list[str] = []
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False):
                    text = shape.text_frame.text
                    if text.strip():
                        parts.append(text)
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        parts.append(" | ".join(cell.text
                                                for cell in row.cells))
            segments.append(Segment(locator=f"slide {index + 1}",
                                    text="\n".join(parts)))
    except Exception as exc:
        raise ExtractionError(f"pptx parse failed: {exc}") from exc
    return segments, {"slides": len(segments)}


# --------------------------------------------------------------- image
def _extract_image(data: bytes) -> tuple[list[Segment], dict]:
    """Metadata only. OCR is not implemented (no OCR engine in
    this environment); no text is returned or invented."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise ExtractionError("Pillow is not installed") from exc
    try:
        with Image.open(io.BytesIO(data)) as image:
            detail = {"image_format": image.format,
                      "width": image.width, "height": image.height,
                      "mode": image.mode, "ocr": "not_implemented"}
    except Exception as exc:
        raise ExtractionError(f"image parse failed: {exc}") from exc
    return [], detail


_HANDLERS = {
    "text": _extract_text, "markdown": _extract_text,
    "code": _extract_text, "csv": _extract_csv, "pdf": _extract_pdf,
    "docx": _extract_docx, "xlsx": _extract_xlsx, "pptx": _extract_pptx,
    "image": _extract_image,
}
