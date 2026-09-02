"""Multi-query retrieval: ask the index the same question several ways, fuse.

Closes the casual-question vs. spec-prose vocabulary gap the retrieval-quality
playbook measured (the "5 seconds" page ranks 1st for the rulebook's own wording
and 9th for a user's). Each rephrasing runs the normal vector search; the ranked
lists merge with the same RRF hybrid retrieval already uses, so a page that any
phrasing ranks highly rises into the fused top-k. Eval-only until recall@k says
it earns the extra LLM call (ADR-0022, same discipline as reranking/ADR-0016).
"""

from __future__ import annotations

import logging

import psycopg

from payments_rag.adapters import query_rewriter
from payments_rag.domain import RetrievedChunk
from payments_rag.retrieval.fusion import reciprocal_rank_fusion
from payments_rag.retrieval.retriever import retrieve

logger = logging.getLogger(__name__)


def retrieve_multi(
    conn: psycopg.Connection, question: str, *, k: int = 5, n_variants: int = 3, fanout: int = 10
) -> list[RetrievedChunk]:
    """Retrieve for the question plus `n_variants` rewrites; RRF-fuse to top `k`.

    `fanout` candidates per phrasing: fusion needs lists wider than `k` so a page
    ranked just below the cutoff for every single phrasing can still win overall.
    A rewriter failure degrades to plain single-query retrieval, never an error -
    the LLM call is an optimization, not a dependency.
    """
    variants = [question]
    try:
        variants += query_rewriter.rewrite(question, n=n_variants)
    except Exception as exc:
        logger.warning("query rewrite failed, falling back to single-query: %s", exc)

    ranked_id_lists: list[list[int]] = []
    by_id: dict[int, RetrievedChunk] = {}
    for variant in variants:
        chunks = retrieve(conn, variant, k=fanout)
        ranked_id_lists.append([c.id for c in chunks])
        for chunk in chunks:
            by_id.setdefault(chunk.id, chunk)

    fused_ids = reciprocal_rank_fusion(ranked_id_lists)[:k]
    return [by_id[cid] for cid in fused_ids]
