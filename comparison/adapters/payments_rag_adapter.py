"""Adapter: payments-rag's own orchestrator, wrapped to the shared shape.

Thin on purpose. No new logic, just calls the same `orchestrator.answer()`
every real user hits and reshapes the result.
"""

from __future__ import annotations

import psycopg

from comparison.schema import SystemAnswer
from payments_rag import orchestrator


def answer(conn: psycopg.Connection, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
    result = orchestrator.answer(conn, question)
    return SystemAnswer(
        system="payments-rag",
        question_id=question_id,
        question=question,
        answer=result.answer,
        contexts=[c.text for c in result.retrieved_chunks],
        citations=[f"{c.source} p{c.page}" for c in result.citations],
        ground_truth=ground_truth,
        latency_s=result.retrieval_s + result.generation_s,
        cost_usd=result.cost_usd,
        raw={
            "retrieval_s": result.retrieval_s,
            "generation_s": result.generation_s,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "retrieved_ids": [c.id for c in result.retrieved_chunks],
            "cited_ids": [c.chunk_id for c in result.citations],
        },
    )
