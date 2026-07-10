"""Answer-quality eval — grade the production answers against the golden set.

For each question: run the production path (orchestrator.answer -> Claude), then
a DIFFERENT model (GPT-4, via judge) scores it against the reference answer —
cross-model (ADR-0007). Costs ~10 Claude + 10 GPT-4 calls per run, so run it
manually/weekly, not per-PR.

    uv run python -m evals.answer_eval [--golden evals/answer_golden_set.yaml]

`summarize()` is left for you to implement (see tests/test_answer_eval.py).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter

import yaml

from evals.judge import judge
from payments_rag.adapters import db
from payments_rag.orchestrator import answer

DEFAULT_GOLDEN = str(Path(__file__).resolve().parent / "answer_golden_set.yaml")
PASS_THRESHOLD = 70


# ===========================================================================
# YOUR TASK — implement summarize(). Pure; tests/test_answer_eval.py checks it.
# ===========================================================================

def summarize(scores: list[int], *, threshold: int = PASS_THRESHOLD) -> tuple[float, float]:
    """Aggregate per-question judge scores into (mean_score, pass_rate).
    """
    if not scores:
        return 0.0, 0.0
    n = len(scores)
    average_score = sum(scores) / n
    pass_rate = sum(1 for s in scores if s >= threshold) / n
    return average_score, pass_rate


# ===========================================================================
# Plumbing (provided).
# ===========================================================================

def _load_golden(path: str | Path) -> list[dict]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []


def _save_results(mean: float, pass_rate: float, details: list[dict], duration_s: float) -> None:
    """Persist the run so the Evals UI can show it without re-paying for a run."""
    out = Path(__file__).resolve().parent.parent / "data" / "last_answer_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "at": datetime.now().isoformat(timespec="seconds"),
                "mean": round(mean, 1),
                "pass_rate": round(pass_rate, 3),
                "threshold": PASS_THRESHOLD,
                "duration_s": duration_s,
                "per_question": details,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def run(golden_path: str | Path = DEFAULT_GOLDEN) -> tuple[float, float]:
    entries = _load_golden(golden_path)
    print(f"\nAnswer eval ({len(entries)} questions) — Claude answers, GPT-4 judges\n")

    scores: list[int] = []
    details: list[dict] = []
    t0 = perf_counter()
    with db.connect() as conn:
        for entry in entries:
            result = answer(conn, entry["question"])
            score, critique = judge(entry["question"], entry["expected_answer"], result.answer)
            scores.append(score)
            details.append({"id": entry["id"], "score": score, "critique": critique})
            print(f"  [{score:3d}]  {entry['id']}  — {critique}")

    duration_s = round(perf_counter() - t0, 2)
    mean, pass_rate = summarize(scores)
    print(
        f"\nmean = {mean:.1f}   pass rate (>= {PASS_THRESHOLD}) = {pass_rate:.0%}   "
        f"({len(scores)} questions in {duration_s}s)\n"
    )
    _save_results(mean, pass_rate, details, duration_s)
    return mean, pass_rate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="evals.answer_eval")
    parser.add_argument("--golden", default=DEFAULT_GOLDEN)
    run(parser.parse_args(argv).golden)


if __name__ == "__main__":
    main()
