"""Comparison harness: payments-rag vs. off-the-shelf RAG systems.

Every system under test answers the same 10 golden-set questions and gets
scored by the same RAGAS metrics (see `evals/ragas_metrics.py`), so no
system's own vendor is also grading it. See `docs/vs-managed-rag.md` for why
these three and not others.

Layout:
    schema.py            shared SystemAnswer record every adapter produces
    adapters/             one module per system, each exposing `answer(question) -> SystemAnswer`
    collect_*.py          scripts: run one adapter over the golden set, write a JSONL log
    score_comparison.py  loads every system's JSONL, scores each row with RAGAS
    report.py             aggregates scores into the committed markdown report
"""
