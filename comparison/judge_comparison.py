"""Grade every collected system's answers with the existing cross-model judge
(`evals/judge.py`, ADR-0007) instead of RAGAS.

Exists because RAGAS's faithfulness/context_precision/context_recall need
retrieved passage text, and NotebookLM's UI only exposes cited filenames
(see `collect/notebooklm.py`'s docstring) — those three scores read as noise
for that system. The judge only needs (question, ground_truth, answer), so
it grades all three systems on the same basis: factual correctness, 0-100.

Resumable like `score_comparison.py` (same content-hash cache-invalidation
approach, see that module's docstring for why a plain (system, question_id) key
isn't enough): a prior `judge_scores.jsonl` is read first, and a row is reused
only if its stored `content_hash` matches a hash of the record's current answer.

Runs in the normal project venv, no isolation needed:

    PYTHONPATH=. python -m comparison.judge_comparison
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from comparison.logging_setup import get_logger
from comparison.schema import read_jsonl
from evals.judge import judge

DATA_DIR = Path("data/comparison")
SYSTEMS = {
    "payments-rag": DATA_DIR / "payments_rag.jsonl",
    "openai-file-search": DATA_DIR / "openai_file_search.jsonl",
    "notebooklm": DATA_DIR / "notebooklm.jsonl",
    "haystack": DATA_DIR / "haystack.jsonl",
    "llamaindex": DATA_DIR / "llamaindex.jsonl",
    "langchain": DATA_DIR / "langchain.jsonl",
}
OUT = DATA_DIR / "judge_scores.jsonl"

log = get_logger("comparison.judge")


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


def _content_hash(answer: str) -> str:
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]


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
            content_hash = _content_hash(r.answer)
            cached = existing.get((system, r.question_id))
            if cached and cached.get("content_hash") == content_hash:
                row = cached
                log.info("%s/%s: cached score=%d", system, r.question_id, row["score"])
            else:
                score, critique = judge(r.question, r.ground_truth, r.answer)
                row = {
                    "system": system,
                    "question_id": r.question_id,
                    "content_hash": content_hash,
                    "score": score,
                    "critique": critique,
                }
                log.info("%s/%s: score=%d (%s)", system, r.question_id, score, critique)
            rows.append(row)
            all_rows.append(row)

        n = len(rows)
        summary[system] = {
            "n": n,
            "mean_score": round(sum(row["score"] for row in rows) / n, 1) if n else 0,
            "pass_rate": round(sum(1 for row in rows if row["score"] >= 70) / n, 2) if n else 0,
        }

    with OUT.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row) + "\n")

    print("\n=== judge summary (factual correctness, 0-100, threshold 70) ===")
    for system, s in summary.items():
        print(f"\n{system} (n={s['n']})")
        print(f"  mean_score: {s['mean_score']}")
        print(f"  pass_rate: {s['pass_rate']}")
    if not summary:
        print("  nothing graded: no collected JSONL files were found")

    log.info("summary: %s", json.dumps(summary))


if __name__ == "__main__":
    run()
