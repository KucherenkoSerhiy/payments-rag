"""In-memory vector store: cosine top-k, pure Python.

No numpy in this project's dependencies and no reason to add one (ADR-0004
spirit): the matrix corpora are a few hundred chunks per topic, so brute-force
cosine over ~600 x 1536-dim vectors per query is milliseconds. Postgres/
pgvector stays untouched - the production index must never be contaminated by
experiment corpora (the article-05 Bug-2 lesson).
"""

from __future__ import annotations

import math

from comparison.matrix.corpus import Chunk


class VectorStore:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._vectors: list[list[float]] = []
        self._norms: list[float] = []

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks vs {len(vectors)} vectors")
        for chunk, vec in zip(chunks, vectors):
            self._chunks.append(chunk)
            self._vectors.append(vec)
            self._norms.append(math.sqrt(sum(x * x for x in vec)))

    def __len__(self) -> int:
        return len(self._chunks)

    def search(self, query_vector: list[float], k: int) -> list[tuple[Chunk, float]]:
        """Top-k chunks by cosine similarity, best first."""
        q_norm = math.sqrt(sum(x * x for x in query_vector))
        if q_norm == 0 or not self._chunks:
            return []
        scored = []
        for chunk, vec, norm in zip(self._chunks, self._vectors, self._norms):
            if norm == 0:
                continue
            dot = sum(a * b for a, b in zip(query_vector, vec))
            scored.append((chunk, dot / (q_norm * norm)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]
