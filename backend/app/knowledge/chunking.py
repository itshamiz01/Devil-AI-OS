"""Deterministic chunking and file intelligence for F06.

Everything here is mechanical and labelled as such: the chunker
packs located segments without ever crossing a locator boundary
(so each chunk cites exactly one page / sheet / slide / line
range); keyphrases are token-frequency statistics; the excerpt
is the highest-overlap sentences VERBATIM. None of this is a
language model and nothing here generates prose (DEF-A2).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import NamedTuple

from ..memory.embeddings import tokenize
from . import constants as C
from .extractors import Segment

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are",
    "was", "were", "be", "been", "for", "on", "with", "as", "by",
    "at", "from", "that", "this", "it", "its", "into", "not", "no",
    "we", "you", "they", "he", "she", "his", "her", "their", "our",
    "your", "will", "would", "can", "could", "should", "than",
    "then", "there", "here", "which", "who", "what", "when",
    "where", "how", "all", "any", "each", "other", "more", "most",
    "such", "only", "also", "over", "after", "before", "between",
}


class Chunk(NamedTuple):
    locator: str
    text: str
    char_start: int
    char_end: int


def document_text(segments: list[Segment]) -> str:
    return "\n".join(seg.text for seg in segments)


def _split_piece(text: str, hard: int) -> list[tuple[int, str]]:
    """Split one segment's text into ≤hard pieces at the last
    newline/space before the limit where possible."""
    pieces: list[tuple[int, str]] = []
    start = 0
    while len(text) - start > hard:
        cut = text.rfind("\n", start, start + hard)
        if cut <= start:
            cut = text.rfind(" ", start, start + hard)
        if cut <= start:
            cut = start + hard
        pieces.append((start, text[start:cut]))
        start = cut
        while start < len(text) and text[start] in " \n":
            start += 1
    if start < len(text):
        pieces.append((start, text[start:]))
    return pieces


def chunk_segments(segments: list[Segment]) -> list[Chunk]:
    chunks: list[Chunk] = []
    offset = 0  # offset of the current segment in the document text
    for segment in segments:
        pieces = _split_piece(segment.text, C.CHUNK_HARD_CHARS)
        buffer: list[tuple[int, str]] = []
        buffer_len = 0
        for piece_start, piece_text in pieces:
            if buffer and buffer_len + len(piece_text) > C.CHUNK_TARGET_CHARS:
                chunks.append(_flush(segment.locator, buffer, offset))
                buffer, buffer_len = [], 0
            buffer.append((piece_start, piece_text))
            buffer_len += len(piece_text)
        if buffer:
            chunks.append(_flush(segment.locator, buffer, offset))
        offset += len(segment.text) + 1  # the joining "\n"
    return chunks


def _flush(locator: str, buffer: list[tuple[int, str]],
           segment_offset: int) -> Chunk:
    text = "\n".join(piece for _start, piece in buffer)
    start = segment_offset + buffer[0][0]
    return Chunk(locator=locator, text=text,
                 char_start=start, char_end=start + len(text))


def keyphrases(text: str, *, limit: int = 15) -> list[dict]:
    """Token-frequency statistics (unigrams + bigrams), labelled
    as statistics — not topics a model inferred."""
    tokens = [t for t in tokenize(text) if t not in STOPWORDS
              and len(t) > 2]
    counts: Counter[str] = Counter(tokens)
    counts.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:])
                if b not in STOPWORDS)
    return [{"phrase": phrase, "count": count}
            for phrase, count in counts.most_common(limit)]


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def extractive_excerpt(text: str, query: str = "", *,
                       sentences: int = 3) -> dict:
    """The highest keyword-overlap sentences, verbatim, in
    original order. Labelled extractive — never a generated
    summary."""
    parts = [s.strip() for s in _SENTENCE_RE.split(text or "")
             if s and s.strip()]
    if not parts:
        return {"method": "deterministic_extract",
                "label": "deterministic extractive excerpt — "
                         "verbatim sentences, not an AI summary",
                "sentences": []}
    terms = set(tokenize(query)) - STOPWORDS if query else set()
    frequencies: Counter[str] = Counter(
        t for t in tokenize(text) if t not in STOPWORDS)

    def score(sentence: str) -> float:
        tokens = [t for t in tokenize(sentence) if t not in STOPWORDS]
        if not tokens:
            return 0.0
        if terms:
            return sum(1 for t in tokens if t in terms) / len(tokens)
        return sum(frequencies[t] for t in tokens) / len(tokens)

    ranked = sorted(range(len(parts)), key=lambda i: -score(parts[i]))
    chosen = sorted(ranked[:sentences])
    return {"method": "deterministic_extract",
            "label": "deterministic extractive excerpt — "
                     "verbatim sentences, not an AI summary",
            "sentences": [parts[i] for i in chosen]}
