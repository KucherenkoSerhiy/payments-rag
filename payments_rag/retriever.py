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
from payments_rag.fusion import reciprocal_rank_fusion


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


def retrieve_hybrid(
    conn: psycopg.Connection, question: str, *, k: int = 5, fanout: int = 20
) -> list[RetrievedChunk]:
    """Hybrid retrieval: fuse semantic (vector) and keyword (FTS) rankings via RRF.

    Pulls `fanout` candidates from each method, fuses their rankings, returns the
    top `k`. `distance` on the results is the vector distance where available
    (nan for keyword-only hits) — it is NOT the fusion score.
    """
    vector_rows = db.nearest(conn, embed_one(question), k=fanout)  # (id, source, text, page, distance)
    keyword_rows = db.keyword_search(conn, question, k=fanout)     # (id, source, text, page, rank)

    by_id: dict[int, RetrievedChunk] = {}
    for cid, source, text, page, dist in vector_rows:
        by_id[cid] = RetrievedChunk(id=cid, source=source, page=page, text=text, distance=dist)
    for cid, source, text, page, _rank in keyword_rows:
        by_id.setdefault(
            cid,
            RetrievedChunk(id=cid, source=source, page=page, text=text, distance=float("nan")),
        )

    vector_ids = [row[0] for row in vector_rows]
    keyword_ids = [row[0] for row in keyword_rows]
    fused_ids = reciprocal_rank_fusion([vector_ids, keyword_ids])[:k]
    return [by_id[cid] for cid in fused_ids]
