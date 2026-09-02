"""Tests for multi-query retrieval: fusion behavior with the LLM and DB faked."""

from __future__ import annotations

from payments_rag.domain import RetrievedChunk
from payments_rag.retrieval import multi_query


def _chunk(cid: int) -> RetrievedChunk:
    return RetrievedChunk(id=cid, source="s.pdf", page=cid, text=f"chunk {cid}", distance=0.1)


def _fake_retrieve(results_by_query: dict[str, list[int]]):
    def fake(conn, question, *, k=5):
        return [_chunk(cid) for cid in results_by_query[question][:k]]
    return fake


def test_agreement_across_variants_beats_a_single_list_top(monkeypatch) -> None:
    # chunk 7 ranks mid-list for every phrasing; chunks 1/2/3 each top one list only.
    monkeypatch.setattr(multi_query.query_rewriter, "rewrite", lambda q, n=3: ["v1", "v2"])
    monkeypatch.setattr(multi_query, "retrieve", _fake_retrieve({
        "q": [1, 7, 8], "v1": [2, 7, 9], "v2": [3, 7, 10],
    }))
    fused = multi_query.retrieve_multi(None, "q", k=2, fanout=3)
    assert fused[0].id == 7


def test_original_question_is_always_one_of_the_variants(monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(multi_query.query_rewriter, "rewrite", lambda q, n=3: ["v1"])

    def spy(conn, question, *, k=5):
        seen.append(question)
        return [_chunk(1)]

    monkeypatch.setattr(multi_query, "retrieve", spy)
    multi_query.retrieve_multi(None, "original", k=1)
    assert seen[0] == "original" and "v1" in seen


def test_rewriter_failure_degrades_to_single_query(monkeypatch) -> None:
    monkeypatch.setattr(
        multi_query.query_rewriter, "rewrite",
        lambda q, n=3: (_ for _ in ()).throw(RuntimeError("api down")),
    )
    monkeypatch.setattr(multi_query, "retrieve", _fake_retrieve({"q": [4, 5, 6]}))
    fused = multi_query.retrieve_multi(None, "q", k=2)
    assert [c.id for c in fused] == [4, 5]  # plain retrieval order, no crash


def test_result_is_capped_at_k_and_deduped(monkeypatch) -> None:
    monkeypatch.setattr(multi_query.query_rewriter, "rewrite", lambda q, n=3: ["v1"])
    monkeypatch.setattr(multi_query, "retrieve", _fake_retrieve({"q": [1, 2, 3], "v1": [2, 1, 3]}))
    fused = multi_query.retrieve_multi(None, "q", k=2, fanout=3)
    ids = [c.id for c in fused]
    assert len(ids) == 2 and len(set(ids)) == 2
