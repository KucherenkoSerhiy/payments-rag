"""Collect payments-rag's own answers via the same orchestrator every real
user request hits:

    PYTHONIOENCODING=utf-8 PYTHONPATH=. python -m comparison.collect.payments_rag
"""

from __future__ import annotations

from comparison.adapters import payments_rag_adapter
from comparison.collect.base import collect, load_golden
from payments_rag.adapters import db


def run() -> None:
    with db.connect() as conn:
        collect(
            "payments-rag",
            load_golden(),
            lambda e: payments_rag_adapter.answer(conn, e["id"], e["question"], e["expected_answer"]),
        )


if __name__ == "__main__":
    run()
