"""Sentence-aware chunker with sentence-level overlap.

Upgraded from the original fixed word-window, which cut mid-sentence and so
produced fragments that embed to fuzzy points. Now we split on sentence
boundaries and pack whole sentences up to ~`size` words, carrying the last
~`overlap` words of trailing sentences into the next chunk so a fact sitting on
a boundary stays retrievable from either side.

Sentence splitting is a simple regex on . ! ? boundaries, good enough for spec
prose. It will mis-split on abbreviations ("e.g.", "No."), an accepted
limitation; a real NLP sentence splitter is a later upgrade if evals show it
matters.
"""

from __future__ import annotations

import re

# Split after a sentence-ending punctuation mark followed by whitespace.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [s for s in (part.strip() for part in _SENTENCE_BREAK.split(text)) if s]


def _words(s: str) -> int:
    return len(s.split())


def _overlap_tail(sentences: list[str], overlap: int) -> tuple[list[str], int]:
    """The trailing sentences whose combined word count fits within `overlap`.

    If even the last sentence alone exceeds `overlap`, return nothing rather than
    duplicating a huge sentence into the next chunk.
    """
    tail: list[str] = []
    words = 0
    for sent in reversed(sentences):
        w = _words(sent)
        if words + w > overlap:
            break
        tail.insert(0, sent)
        words += w
    return tail, words


def chunk_text(text: str, *, size: int = 300, overlap: int = 50) -> list[str]:
    """Split text into ~`size`-word chunks aligned to sentence boundaries, with
    ~`overlap` words shared between consecutive chunks. Returns [] for empty input.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be >= 0 and < size")

    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    words = 0
    for sent in sentences:
        w = _words(sent)
        # Flush before this sentence would push us over the target, but only if
        # we already have content (a single over-size sentence becomes its own chunk).
        if current and words + w > size:
            chunks.append(" ".join(current))
            current, words = _overlap_tail(current, overlap)
        current.append(sent)
        words += w

    if current:
        chunks.append(" ".join(current))
    return chunks
