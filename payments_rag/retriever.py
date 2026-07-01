"""Retriever: question -> top-k relevant chunks.

The query half of the RAG loop. It embeds the question with the same pinned
model used at index time and asks pgvector for the nearest chunks. It does NOT
generate an answer — that is the Week-3 agent layer. Keeping retrieval separate
means a bad result can be diagnosed as a retrieval failure vs a generation one.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from payments_rag import db
from payments_rag.embedding import embed_one


@dataclass
class RetrievedChunk:
    id: int
    source: str
    page: int | None
    text: str
    distance: float  # cosine distance, 0 = identical direction


def retrieve(
    conn: psycopg.Connection, question: str, *, k: int = 5
) -> list[RetrievedChunk]:
    """Embed the question and return the k nearest chunks, closest first."""
    qvec = embed_one(question)
    rows = db.nearest(conn, qvec, k=k)
    # db.nearest rows are (id, source, text, page, distance)
    return [
        RetrievedChunk(id=r[0], source=r[1], page=r[3], text=r[2], distance=r[4])
        for r in rows
    ]
