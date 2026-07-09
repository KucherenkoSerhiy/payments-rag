"""Tests for the pure reranking reorder — order_by_relevance. No DB, no API."""

from __future__ import annotations

import pytest

from payments_rag.retrieval import rerank
from payments_rag.retrieval.rerank import order_by_relevance
from payments_rag.retrieval.retriever import RetrievedChunk


def _chunk(cid: int) -> RetrievedChunk:
    return RetrievedChunk(id=cid, source="s", page=1, text=f"chunk {cid}", distance=0.0)


def test_reorders_by_score_desc() -> None:
    a, b, c = _chunk(1), _chunk(2), _chunk(3)
    assert order_by_relevance([a, b, c], [10, 90, 50], k=3) == [b, c, a]


def test_takes_top_k() -> None:
    a, b, c = _chunk(1), _chunk(2), _chunk(3)
    assert order_by_relevance([a, b, c], [10, 90, 50], k=2) == [b, c]


def test_ties_keep_original_order() -> None:
    a, b, c = _chunk(1), _chunk(2), _chunk(3)
    # a and b both score 50; a came first, so it stays first (stable)
    assert order_by_relevance([a, b, c], [50, 50, 10], k=2) == [a, b]


def test_k_larger_than_candidates_returns_all() -> None:
    a, b = _chunk(1), _chunk(2)
    assert order_by_relevance([a, b], [30, 70], k=5) == [b, a]


def test_empty_is_empty() -> None:
    assert order_by_relevance([], [], k=3) == []


def test_mismatched_lengths_raise() -> None:
    # scores pair 1:1 with candidates; a length mismatch is a wiring bug, and
    # zip(strict=True) makes it fail loudly instead of dropping the extra tail.
    with pytest.raises(ValueError):
        order_by_relevance([_chunk(1), _chunk(2)], [50], k=2)


# ---------------------------------------------------------------------------
# rerank_retrieve — the wiring. We never stub `conn`; we stub the two seams
# that consume it (retrieve) and hit the API (relevance), so conn is an inert
# pass-through and None is fine. rerank.py imports the *modules*:
#     from payments_rag.retrieval import retriever
#     from payments_rag.adapters import reranker
# so we patch retrieve/relevance on those module objects (patch where USED).
# ---------------------------------------------------------------------------

def test_rerank_retrieve_reorders_candidates(monkeypatch) -> None:
    candidates = [_chunk(1), _chunk(2), _chunk(3)]
    monkeypatch.setattr(rerank.retriever, "retrieve", lambda conn, question, *, k: candidates)
    # cross-encoder: chunk 3 is most relevant, then 1, then 2
    by_id = {1: 40, 2: 10, 3: 90}
    monkeypatch.setattr(rerank.reranker, "relevance", lambda q, passage: by_id[int(passage.split()[-1])])

    out = rerank.rerank_retrieve(None, "some question", k=2, fanout=3)

    assert [c.id for c in out] == [3, 1]


def test_rerank_retrieve_fetches_fanout_then_trims_to_k(monkeypatch) -> None:
    seen: dict[str, int] = {}

    def fake_retrieve(conn, question, *, k):
        seen["k"] = k
        return [_chunk(i) for i in range(1, 6)]  # 5 candidates

    monkeypatch.setattr(rerank.retriever, "retrieve", fake_retrieve)
    monkeypatch.setattr(rerank.reranker, "relevance", lambda q, passage: int(passage.split()[-1]))  # score = id

    out = rerank.rerank_retrieve(None, "q", k=2, fanout=5)

    assert seen["k"] == 5                  # fetched the fanout, not k
    assert [c.id for c in out] == [5, 4]   # top 2 by relevance (= id)
