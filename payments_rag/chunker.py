"""Word-window chunker with overlap.

Deliberately simple for the W1 spike. Real chunking strategy (section-aware,
ISO 20022 cross-reference handling) is a Week-2 concern; scoping risk #5 flags
it as the likely 2-3 iteration problem. This version is what the unit test pins.
"""

from __future__ import annotations


def chunk_text(text: str, *, size: int = 300, overlap: int = 50) -> list[str]:
    """Split text into ~`size`-word chunks, each sharing `overlap` words with
    the previous one.

    Overlap keeps a sentence that straddles a boundary retrievable from either
    side. Returns [] for empty/whitespace input.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be >= 0 and < size")

    words = text.split()
    if not words:
        return []

    step = size - overlap
    chunks: list[str] = []
    for start in range(0, len(words), step):
        window = words[start : start + size]
        chunks.append(" ".join(window))
        if start + size >= len(words):
            break  # last window reached the end; don't emit trailing overlap-only chunks
    return chunks
