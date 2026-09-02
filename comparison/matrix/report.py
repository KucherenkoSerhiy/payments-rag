"""Aggregate the matrix run into the tables the article needs. Free, no API.

Produces data/matrix/summary.json plus a printed digest:

  * per (pipeline, topic): mean judge score per judge, pass rate (>= 70,
    the project-wide bar), mean latency, total cost;
  * per pipeline overall: the same, across all topics;
  * the judge x generator-vendor matrix: mean score each judge family gives
    each generator family. The diagonal (same vendor judging its own family's
    output) vs the off-diagonal IS the self-preference-bias measurement.

Pass-rate and means use each judge separately - scores from different judges
are never averaged together into one number, because "the three judges
disagree" is a finding, not noise to smooth away.

    PYTHONPATH=. PYTHONIOENCODING=utf-8 python -m comparison.matrix.report
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from comparison.matrix.config import CHAT_MODELS, PIPELINES

ANSWERS = Path("data/matrix/answers.jsonl")
SCORES = Path("data/matrix/judge_scores.jsonl")
OUT = Path("data/matrix/summary.json")

PASS_BAR = 70  # same threshold as evals/answer_eval.py and article 05


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def run() -> None:
    answers = _read_jsonl(ANSWERS)
    scores = _read_jsonl(SCORES)
    if not answers:
        print(f"nothing to report: {ANSWERS} is empty or missing")
        return

    pipeline_chat = {p.key: CHAT_MODELS[p.chat] for p in PIPELINES}

    # --- per (pipeline, topic) and per pipeline ------------------------------
    by_cell: dict[tuple[str, str], dict] = {}
    for a in answers:
        cell = by_cell.setdefault((a["pipeline"], a["topic"]), {
            "n": 0, "cost_usd": 0.0, "latency": [], "judges": defaultdict(list),
        })
        cell["n"] += 1
        cell["cost_usd"] += a["cost_usd"]
        cell["latency"].append(a["latency_s"])
    for s in scores:
        cell = by_cell.get((s["pipeline"], s["topic"]))
        if cell is not None:
            cell["judges"][s["judge"]].append(s["score"])

    summary: dict = {"cells": [], "pipelines": {}, "judge_vendor_matrix": {}}
    for (pipeline, topic), cell in sorted(by_cell.items()):
        row = {
            "pipeline": pipeline,
            "topic": topic,
            "n": cell["n"],
            "total_cost_usd": round(cell["cost_usd"], 4),
            "mean_latency_s": _mean(cell["latency"]),
            "judges": {
                judge: {
                    "mean": _mean(vals),
                    "pass_rate": round(sum(v >= PASS_BAR for v in vals) / len(vals), 2),
                }
                for judge, vals in sorted(cell["judges"].items())
            },
        }
        summary["cells"].append(row)

    for pipe in PIPELINES:
        rows = [c for c in summary["cells"] if c["pipeline"] == pipe.key]
        if not rows:
            continue
        judges = sorted({j for r in rows for j in r["judges"]})
        summary["pipelines"][pipe.key] = {
            "topics": len(rows),
            "total_cost_usd": round(sum(r["total_cost_usd"] for r in rows), 4),
            "mean_latency_s": _mean([r["mean_latency_s"] for r in rows]),
            "judges": {
                j: _mean([r["judges"][j]["mean"] for r in rows if j in r["judges"]])
                for j in judges
            },
        }

    # --- judge-vendor x generator-vendor matrix ------------------------------
    vendor_scores: dict[tuple[str, str], list[int]] = defaultdict(list)
    for s in scores:
        gen_vendor = pipeline_chat[s["pipeline"]].provider
        judge_vendor = CHAT_MODELS[s["judge"]].provider
        vendor_scores[(judge_vendor, gen_vendor)].append(s["score"])
    for (judge_vendor, gen_vendor), vals in sorted(vendor_scores.items()):
        summary["judge_vendor_matrix"].setdefault(judge_vendor, {})[gen_vendor] = {
            "mean": _mean(vals),
            "n": len(vals),
            "self_judging": judge_vendor == gen_vendor,
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # --- printed digest ------------------------------------------------------
    print(f"\n=== matrix summary ({len(answers)} answers, {len(scores)} judge rows) ===")
    for key, p in summary["pipelines"].items():
        judge_bits = ", ".join(f"{j}={v}" for j, v in p["judges"].items())
        print(f"\n{key} ({p['topics']} topics, ${p['total_cost_usd']}, {p['mean_latency_s']}s avg)")
        print(f"  judge means: {judge_bits}")
    if summary["judge_vendor_matrix"]:
        print("\njudge-vendor x generator-vendor mean score (D = self-judging diagonal):")
        for judge_vendor, row in summary["judge_vendor_matrix"].items():
            bits = ", ".join(
                f"{gv}={v['mean']}{'(D)' if v['self_judging'] else ''}"
                for gv, v in row.items()
            )
            print(f"  judged by {judge_vendor}: {bits}")
    print(f"\nwritten to {OUT}")


if __name__ == "__main__":
    run()
