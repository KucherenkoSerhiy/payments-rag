"""Score every collected system's answers with the same RAGAS metrics.

Reads whichever of the three `data/comparison/*.jsonl` files exist (a missing
one is logged and skipped, not an error, since NotebookLM's leg may not be
collected yet) and writes one combined scored file plus a printed summary.

Resumable: a prior `ragas_scores.jsonl` is read first, and a row is reused only if
it's complete (all four metrics present and non-NaN) AND its stored `content_hash`
matches a hash of the record's current `(answer, contexts)` - so a row is retried
both when it failed last time and when the underlying collected answer changed
since (e.g. after re-indexing the corpus). An earlier version of this cache keyed
purely on `(system, question_id)`, which silently reused stale scores after a
corpus fix changed the answers underneath - caught only because a rescore finished
suspiciously fast with numbers identical to the previous run. Content-hashing closes
that gap without needing every caller to remember to hand-clear stale rows first.

Runs isolated, same as `evals.ragas_eval` (see that module's docstring for why):

    PYTHONPATH=. uv run --isolated --with "ragas==0.4.3" \\
        --with "langchain-community<0.3" --with langchain-openai \\
        --with python-dotenv \\
        python -m comparison.score_comparison
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from comparison.logging_setup import get_logger
from comparison.schema import read_jsonl
from evals.ragas_metrics import score_one

DATA_DIR = Path("data/comparison")
SYSTEMS = {
    "payments-rag": DATA_DIR / "payments_rag.jsonl",
    "openai-file-search": DATA_DIR / "openai_file_search.jsonl",
    "notebooklm": DATA_DIR / "notebooklm.jsonl",
    "haystack": DATA_DIR / "haystack.jsonl",
    "llamaindex": DATA_DIR / "llamaindex.jsonl",
    "langchain": DATA_DIR / "langchain.jsonl",
}
OUT = DATA_DIR / "ragas_scores.jsonl"
METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")

log = get_logger("comparison.score")


def _load_existing(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    existing = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        existing[(row["system"], row["question_id"])] = row
    return existing


def _is_complete(row: dict) -> bool:
    return all(row.get(k) is not None and row[k] == row[k] for k in METRICS)  # nan != nan


def _content_hash(answer: str, contexts: list[str]) -> str:
    payload = json.dumps({"answer": answer, "contexts": contexts}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _mean(values: list[float]) -> float:
    good = [v for v in values if v == v]  # drop NaN
    return round(sum(good) / len(good), 3) if good else float("nan")


def run() -> None:
    existing = _load_existing(OUT)
    all_rows: list[dict] = []
    summary: dict[str, dict] = {}

    for system, path in SYSTEMS.items():
        if not path.exists():
            log.info("%s: no data yet (%s missing), skipped", system, path)
            continue

        records = read_jsonl(path)
        rows = []
        for r in records:
            content_hash = _content_hash(r.answer, r.contexts)
            cached = existing.get((system, r.question_id))
            if cached and _is_complete(cached) and cached.get("content_hash") == content_hash:
                row = cached
                log.info("%s/%s: cached faithfulness=%.2f", system, r.question_id, row["faithfulness"])
            else:
                score = score_one(r.question, r.contexts, r.answer, r.ground_truth)
                row = {
                    "system": system,
                    "question_id": r.question_id,
                    "content_hash": content_hash,
                    "cost_usd": r.cost_usd,
                    "latency_s": r.latency_s,
                    "faithfulness": round(score.faithfulness, 3),
                    "answer_relevancy": round(score.answer_relevancy, 3),
                    "context_precision": round(score.context_precision, 3),
                    "context_recall": round(score.context_recall, 3),
                }
                log.info("%s/%s: faithfulness=%.2f", system, r.question_id, score.faithfulness)
            rows.append(row)
            all_rows.append(row)

        n = len(rows)
        summary[system] = {
            "n": n,
            "n_incomplete": sum(1 for row in rows if not _is_complete(row)),
            "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
            "mean_latency_s": round(sum(r["latency_s"] for r in rows) / n, 2) if n else 0,
            **{k: _mean([row[k] for row in rows]) for k in METRICS},
        }

    with OUT.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row) + "\n")

    print("\n=== comparison summary ===")
    for system, s in summary.items():
        print(f"\n{system} (n={s['n']}, ${s['total_cost_usd']}, {s['mean_latency_s']}s avg)")
        if s["n_incomplete"]:
            print(f"  WARNING: {s['n_incomplete']} row(s) still incomplete (NaN metric) after this run")
        for k in METRICS:
            print(f"  {k}: {s[k]}")
    if not summary:
        print("  nothing scored: no collected JSONL files were found")

    log.info("summary: %s", json.dumps(summary))


if __name__ == "__main__":
    run()
