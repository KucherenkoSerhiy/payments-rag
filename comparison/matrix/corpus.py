"""Topic corpus loading and chunking for the model matrix.

Reads the converted plain-text corpus (corpus/topics/<topic>/*.txt|*.md,
produced by scripts/fetch_topic_corpus.py + scripts/convert_topic_corpus.py)
and chunks by words: 200-word chunks with 20-word overlap - the same
standardization article 05 anchored all its framework comparators on, kept
frozen here so chunking never becomes a hidden variable again.

Also provides a corpus fingerprint (hash of every file's content) that the
runner folds into its cache key: if the corpus changes, every cached answer
for that topic is invalidated automatically - the exact failure mode the
article-05 incident writeup documented.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from comparison.matrix.config import CHUNK_OVERLAP_WORDS, CHUNK_WORDS

TOPICS_DIR = Path("corpus/topics")


@dataclass(frozen=True)
class Chunk:
    source: str  # file name the chunk came from (the citation unit)
    text: str


def _topic_files(topic: str) -> list[Path]:
    topic_dir = TOPICS_DIR / topic
    files = sorted(
        p for p in topic_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".txt", ".md"}
    )
    if not files:
        raise FileNotFoundError(
            f"no corpus files under {topic_dir} - run scripts/fetch_topic_corpus.py "
            "and scripts/convert_topic_corpus.py first"
        )
    return files


def load_chunks(topic: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    step = CHUNK_WORDS - CHUNK_OVERLAP_WORDS
    for path in _topic_files(topic):
        words = path.read_text(encoding="utf-8").split()
        for start in range(0, len(words), step):
            piece = words[start:start + CHUNK_WORDS]
            if len(piece) < 20 and start > 0:  # skip a trailing sliver
                break
            chunks.append(Chunk(source=path.name, text=" ".join(piece)))
    return chunks


def fingerprint(topic: str) -> str:
    """Stable hash of the topic's corpus content (order-independent per file)."""
    h = hashlib.sha256()
    for path in _topic_files(topic):
        h.update(path.name.encode())
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()[:16]
