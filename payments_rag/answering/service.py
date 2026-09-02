from __future__ import annotations

import logging

import psycopg

from payments_rag import query_log
from payments_rag.adapters import db
from payments_rag.answering.orchestrator import answer
from payments_rag.domain import AnswerResult

logger = logging.getLogger(__name__)


def ask(conn: psycopg.Connection, question: str, *, k: int = 5) -> AnswerResult:
    """Answer a question, record its cost in the wallet ledger, log telemetry."""
    result = answer(conn, question, k=k)
    try:
        db.wallet_add_spend(conn, result.cost_usd)
    except Exception as exc:
        # The answer is already paid for; a ledger hiccup must not fail it.
        logger.warning("spend not recorded (%.6f USD): %s", result.cost_usd, exc)
    query_log.log_query(
        question,
        mode="vector",
        k=k,
        wall_s=result.retrieval_s + result.generation_s,
        retrieval_s=result.retrieval_s,
        generation_s=result.generation_s,
        n_citations=len(result.citations),
        cost_usd=result.cost_usd,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    return result
