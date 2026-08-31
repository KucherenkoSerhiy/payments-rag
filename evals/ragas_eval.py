"""RAGAS eval: score payments-rag's own answers with faithfulness, answer
relevancy, context precision, and context recall.

Reuses `data/comparison/payments_rag.jsonl` (written by
`comparison.collect_payments_rag`, the same golden-set run `evals.answer_eval`
uses) rather than re-querying the LLM: RAGAS needs the *same* system to answer
either way, and re-collecting would just spend Claude tokens twice for the
identical result. Run the collector first if that file doesn't exist yet.

This script imports `ragas_metrics`, which hard-pulls in langchain (ADR-0004
says this project stays langchain-free). It is never run from the main venv:

    PYTHONPATH=. uv run --isolated --with "ragas==0.4.3" \\
        --with "langchain-community<0.3" --with langchain-openai \\
        --with python-dotenv --with pyyaml \\
        python -m evals.ragas_eval
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from evals.ragas_metrics import score_one
from comparison.schema import read_jsonl

ANSWERS = Path("data/comparison/payments_rag.jsonl")
OUT = Path("data/last_ragas_eval.json")


def run() -> None:
    if not ANSWERS.exists():
        raise FileNotFoundError(
            f"{ANSWERS} not found. Run `PYTHONPATH=. python -m comparison.collect_payments_rag` first."
        )
    records = read_jsonl(ANSWERS)
    print(f"\nRAGAS eval on payments-rag's own answers ({len(records)} questions)\n")

    details: list[dict] = []
    for r in records:
        score = score_one(r.question, r.contexts, r.answer, r.ground_truth)
        details.append({
            "id": r.question_id,
            "faithfulness": round(score.faithfulness, 3),
            "answer_relevancy": round(score.answer_relevancy, 3),
            "context_precision": round(score.context_precision, 3),
            "context_recall": round(score.context_recall, 3),
        })
        print(
            f"  {r.question_id}: faithfulness={score.faithfulness:.2f} "
            f"relevancy={score.answer_relevancy:.2f} "
            f"precision={score.context_precision:.2f} recall={score.context_recall:.2f}"
        )

    n = len(details)
    means = {
        k: round(sum(d[k] for d in details) / n, 3)
        for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
    } if n else {}
    print(f"\nmeans: {means}\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"at": datetime.now().isoformat(timespec="seconds"), "means": means, "per_question": details},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"written to {OUT}")


if __name__ == "__main__":
    run()
