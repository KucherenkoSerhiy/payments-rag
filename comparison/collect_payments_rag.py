"""Collect payments-rag's own answers over the golden set, in the shared
comparison shape. Reuses the exact same golden set and orchestrator every
production query hits; no new logic, just logging it alongside the other
systems for a fair comparison.

    PYTHONIOENCODING=utf-8 PYTHONPATH=. python -m comparison.collect_payments_rag
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import yaml

from comparison.adapters import payments_rag_adapter
from comparison.logging_setup import get_logger
from comparison.schema import append_jsonl
from payments_rag.adapters import db

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "answer_golden_set.yaml"
OUT = Path("data/comparison/payments_rag.jsonl")

log = get_logger("comparison.collect_payments_rag")


def run() -> None:
    entries = yaml.safe_load(GOLDEN.read_text(encoding="utf-8")) or []
    log.info("starting payments-rag collection: %d questions", len(entries))
    OUT.unlink(missing_ok=True)  # fresh run each time, not appended to a stale file

    t0 = perf_counter()
    with db.connect() as conn:
        for entry in entries:
            record = payments_rag_adapter.answer(conn, entry["id"], entry["question"], entry["expected_answer"])
            append_jsonl(OUT, record)
            log.info("%s: %.2fs, $%.5f", entry["id"], record.latency_s, record.cost_usd)

    log.info("done: %d questions in %.1fs, written to %s", len(entries), perf_counter() - t0, OUT)


if __name__ == "__main__":
    run()
