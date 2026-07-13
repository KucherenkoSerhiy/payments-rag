"""Reranking: a cheap first pass fetches many, a sharp second pass reorders.

The problem, from our own numbers: retrieval is recall-bound, recall@5 = 0.60
but @20 = 0.70, so for ~1 question in 10 the right page IS fetched, just ranked
too low to reach the top 5. Reranking targets exactly that: pull a wider `fanout`,
rescore each candidate with a stronger (slower) model, keep the best `k`. It only
reorders what was already fetched; a page missed even at 20 stays a recall
problem, not a ranking one.

Bi-encoder vs cross-encoder: the bi-encoder (embedding.py) embeds question and
passage separately (fast, whole-corpus, but never sees them together); the
cross-encoder (adapters/reranker.py) reads the pair together for one score,
sharper, but one call per pair, so it runs only over the fanout.

DISCLAIMER: eval-only. Our cross-encoder is an LLM call, so a fanout is a
sequential burst of calls (~1 min/query), too slow for the interactive path. A
production reranker would be a local, batched cross-encoder. See ADR-0016.
"""

from __future__ import annotations

import psycopg

from payments_rag.adapters import reranker
from payments_rag.retrieval import retriever
from payments_rag.retrieval.retriever import RetrievedChunk


def rerank_retrieve(
    conn: psycopg.Connection, question: str, *, k: int = 5, fanout: int = 20
) -> list[RetrievedChunk]:
    """Fetch `fanout` candidates (bi-encoder), rescore with the cross-encoder, return top `k`."""
    candidates = retriever.retrieve(conn, question, k=fanout)
    scores = [reranker.relevance(question, c.text) for c in candidates]
    return order_by_relevance(candidates, scores, k=k)


def order_by_relevance(
    candidates: list[RetrievedChunk], scores: list[int], *, k: int
) -> list[RetrievedChunk]:
    """Reorder `candidates` by `scores` (higher first, stable on ties); return top `k`."""
    sorted_list = sorted(zip(scores, candidates, strict=True), key=lambda x: x[0], reverse=True)
    sorted_candidates = [c for _, c in sorted_list]
    return sorted_candidates[:k]
