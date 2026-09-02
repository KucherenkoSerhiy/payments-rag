"""Aggregate both scorers' outputs into the comparison report.

The numbers previously traveled into prose by hand; this makes them
regenerable in one command and writes the committed receipt:

    PYTHONPATH=. PYTHONIOENCODING=utf-8 python -m comparison.report
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

DATA_DIR = Path("data/comparison")
RAGAS = DATA_DIR / "ragas_scores.jsonl"
JUDGE = DATA_DIR / "judge_scores.jsonl"
OUT = Path("docs/comparison-report.md")

PASS_THRESHOLD = 70  # same bar as evals/answer_eval.py

# NotebookLM's UI exposes only cited filenames, not passage text, so the three
# context-dependent RAGAS metrics score noise for it (see collect/notebooklm.py).
CONTEXT_METRICS = ("faithfulness", "context_precision", "context_recall")
NO_CONTEXT_SYSTEMS = {"notebooklm"}


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run the collectors and scorers first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _mean(values: list[float]) -> float:
    good = [v for v in values if v == v]  # drop NaN
    return sum(good) / len(good) if good else float("nan")


def summarize() -> list[dict]:
    """One row per system: judge mean/pass rate + RAGAS means + cost/latency."""
    by_system: dict[str, dict] = {}
    for row in _rows(RAGAS):
        s = by_system.setdefault(row["system"], {"ragas": [], "judge": []})
        s["ragas"].append(row)
    for row in _rows(JUDGE):
        by_system.setdefault(row["system"], {"ragas": [], "judge": []})["judge"].append(row)

    summaries = []
    for system, data in by_system.items():
        ragas, judge = data["ragas"], data["judge"]
        scores = [r["score"] for r in judge]
        summary = {
            "system": system,
            "n": len(judge) or len(ragas),
            "judge_mean": round(_mean(scores), 1),
            "judge_pass_rate": round(sum(1 for s in scores if s >= PASS_THRESHOLD) / len(scores), 2) if scores else None,
            "total_cost_usd": round(sum(r["cost_usd"] for r in ragas), 4),
            "mean_latency_s": round(_mean([r["latency_s"] for r in ragas]), 2),
            "answer_relevancy": round(_mean([r["answer_relevancy"] for r in ragas]), 3),
        }
        for metric in CONTEXT_METRICS:
            summary[metric] = (
                None if system in NO_CONTEXT_SYSTEMS
                else round(_mean([r[metric] for r in ragas]), 3)
            )
        summaries.append(summary)

    summaries.sort(key=lambda s: s["judge_mean"], reverse=True)
    return summaries


def render(summaries: list[dict]) -> str:
    def cell(value, fmt: str) -> str:
        return "-" if value is None else format(value, fmt)

    lines = [
        "# Comparison report",
        "",
        f"Generated {date.today().isoformat()} by `python -m comparison.report` from",
        "`data/comparison/ragas_scores.jsonl` and `judge_scores.jsonl`. Do not edit by",
        "hand - rerun instead. Ordered by judge score, the primary metric.",
        "",
        "| System | n | Judge (0-100) | Pass >=70 | Faithfulness | Relevancy | Precision | Recall | Cost (10 q) | Latency |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        lines.append(
            f"| {s['system']} | {s['n']} | {s['judge_mean']:.1f} | {s['judge_pass_rate']:.0%} "
            f"| {cell(s['faithfulness'], '.3f')} | {s['answer_relevancy']:.3f} "
            f"| {cell(s['context_precision'], '.3f')} | {cell(s['context_recall'], '.3f')} "
            f"| ${s['total_cost_usd']:.4f} | {s['mean_latency_s']:.2f}s |"
        )
    lines += [
        "",
        "Notes:",
        "- notebooklm's faithfulness/precision/recall are `-`, not zero: its UI exposes",
        "  only cited filenames, so those metrics score noise (see comparison/collect/notebooklm.py).",
        "  Its latency is an operator-observed approximation and its cost excludes ~11 min",
        "  of manual setup.",
        "- Judge = cross-model factual correctness vs the golden reference (evals/judge.py).",
        "  RAGAS columns = mechanics: grounding, topicality, retrieval precision/recall.",
    ]
    return "\n".join(lines) + "\n"


def run() -> None:
    report = render(summarize())
    OUT.write_text(report, encoding="utf-8")
    print(report)
    print(f"written to {OUT}")


if __name__ == "__main__":
    run()
