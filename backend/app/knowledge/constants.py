"""Constants for Personal Knowledge & File Intelligence (F06).

House discipline: every value the feature decides with is named
here — formats and their honest support states, size and chunking
bounds, document/chunk lifecycle vocabularies. Support states use
the F02 framework's one honest vocabulary where a state is a
configuration fact (``requires_owner_configuration`` is not one
here; extraction support is ``supported`` /
``metadata_only_ocr_not_implemented`` / ``unsupported_format``,
probed at runtime from the installed extractors).
"""
from __future__ import annotations

# Byte ceiling for one uploaded/indexed file. Bounded processing
# is a P-05 rule this feature keeps.
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MiB

# Chunking: located segments are packed toward TARGET and never
# past HARD; a chunk never crosses a locator boundary, so each
# chunk carries exactly one citation locator.
CHUNK_TARGET_CHARS = 1200
CHUNK_HARD_CHARS = 2000

# Folder indexing is confined to this directory under the data
# dir. The owner authorizes a folder by placing it there and
# naming it in an owner-only call; nothing outside is reachable.
IMPORT_DIRNAME = "knowledge-import"
STORAGE_DIRNAME = "knowledge-files"

# Format detection is by extension (the name the owner gave the
# file), cross-checked by the extractor's own parser at read time:
# a file whose bytes do not parse as its claimed format fails
# extraction honestly rather than yielding invented text.
FORMAT_BY_EXTENSION = {
    ".txt": "text", ".md": "markdown", ".markdown": "markdown",
    ".csv": "csv", ".log": "text",
    ".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".bmp": "image", ".webp": "image",
    ".py": "code", ".js": "code", ".ts": "code", ".tsx": "code",
    ".jsx": "code", ".json": "code", ".yaml": "code", ".yml": "code",
    ".toml": "code", ".sh": "code", ".sql": "code", ".html": "code",
    ".css": "code", ".java": "code", ".go": "code", ".rs": "code",
    ".c": "code", ".h": "code", ".cpp": "code", ".rb": "code",
    ".php": "code",
}

TEXT_FORMATS = ("text", "markdown", "code")
SUPPORTED_FORMATS = TEXT_FORMATS + ("csv", "pdf", "docx", "xlsx", "pptx")

# Document lifecycle (knowledge_documents.status).
DOC_STATUSES = (
    "indexed",             # every chunk stored (or an exact duplicate link)
    "partially_indexed",   # some chunks stored, some rejected by P-09 policy
    "duplicate",           # bytes identical to an earlier live document
    "excluded",            # matched the collection's exclusion patterns
    "unsupported_format",  # no extractor for this format
    "metadata_only",       # images: metadata recorded, OCR not implemented
    "empty",               # extraction succeeded; no text found
    "extraction_failed",   # the real parser refused the bytes
    "rejected_sensitive",  # every chunk blocked by P-09's secret screen
)

# Chunk ingestion outcomes (knowledge_chunks.index_status) — the
# P-09 ingestion job vocabulary, mapped once, here.
CHUNK_STATUSES = (
    "stored",              # P-09 STORED
    "duplicate",           # P-09 REJECTED_DUPLICATE (exact chunk seen before)
    "rejected_low_value",  # P-09 REJECTED_LOW_VALUE (usefulness filter)
    "rejected_sensitive",  # P-09 REJECTED_SENSITIVE (secret screen)
)

EMBEDDER_CAVEAT = (
    "retrieval runs over P-09's local-hash-v1 embedder: a lexical "
    "approximation (hashed token/trigram overlap), not a neural "
    "semantic model; a real embedding model is DEF-A2 / "
    "owner-machine work")
