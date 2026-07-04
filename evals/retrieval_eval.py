"""Retrieval eval — measures recall@k of the retriever against the golden set.

Retrieval-only: no LLM, no answer generation. For each labelled question it asks
"did the retriever surface a truly-relevant page within the top k?", then
reports the fraction that did (recall@k).

    uv run python -m evals.retrieval_eval [-k 5] [--golden evals/retrieval_golden_set.yaml]

TWO FUNCTIONS ARE LEFT FOR YOU TO IMPLEMENT: `hit_at_k` and `recall_at_k`.
Everything around them (loading the golden set, calling the retriever, printing)
is done. Workflow:
    1. Implement the two functions below.
    2. uv run pytest tests/test_retrieval_eval.py   # until green
    3. Label some answer_pages in the golden set, then run this script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from payments_rag import db
from payments_rag.retriever import retrieve

DEFAULT_GOLDEN = "evals/retrieval_golden_set.yaml"


# ===========================================================================
# YOUR TASK — implement these two pure functions.
# They take plain data (tuples, bools), so tests/test_retrieval_eval.py can
# check them with no DB and no API calls.
# ===========================================================================

def hit_at_k(
    retrieved: list[tuple[str, int]],
    expected: set[tuple[str, int]],
    k: int,
) -> bool:
    """Did retrieval find a relevant page within the top k?

    retrieved: (source, page) pairs ordered BEST-first (rank 1 is index 0).
    expected:  the set of (source, page) pairs that truly answer the question.
    k:         how many of the top results count.

    Return True if ANY of the first `k` retrieved pairs is in `expected`;
    otherwise False. (This is "recall-style" hit detection: one relevant hit in
    the top k is enough.)
    """
    for pair in retrieved[:k]:
        if pair in expected:
            return True

    return False


def recall_at_k(hit_flags: list[bool]) -> float:
    if not hit_flags:
        return 0.0
    return sum(hit_flags) / len(hit_flags)


# ===========================================================================
# Plumbing (provided) — wires the retriever to your functions.
# ===========================================================================

def _load_golden(path: str | Path) -> list[dict]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []


def _expected_pairs(entry: dict) -> set[tuple[str, int]]:
    """Flatten an entry's answer_pages into a set of (source, page) pairs."""
    pairs: set[tuple[str, int]] = set()
    for block in entry.get("answer_pages", []):
        for page in block.get("pages", []):
            pairs.add((block["source"], int(page)))
    return pairs


def run(golden_path: str | Path = DEFAULT_GOLDEN, k: int = 5) -> float:
    entries = _load_golden(golden_path)
    print(f"\nRetrieval eval @k={k}  ({len(entries)} questions)\n")

    hit_flags: list[bool] = []
    with db.connect() as conn:
        for entry in entries:
            expected = _expected_pairs(entry)
            if not expected:
                print(f"  [SKIP] {entry['id']}: no answer_pages labelled yet")
                continue
            results = retrieve(conn, entry["question"], k=k)
            retrieved = [(r.source, r.page) for r in results]
            hit = hit_at_k(retrieved, expected, k)
            hit_flags.append(hit)
            print(f"  [{'HIT ' if hit else 'MISS'}] {entry['id']}")

    score = recall_at_k(hit_flags)
    print(
        f"\nrecall@{k} = {score:.2f}  "
        f"({sum(hit_flags)}/{len(hit_flags)} answered questions)\n"
    )
    return score


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="evals.retrieval_eval")
    parser.add_argument("-k", type=int, default=5, help="top-k to score against")
    parser.add_argument("--golden", default=DEFAULT_GOLDEN)
    args = parser.parse_args(argv)
    run(args.golden, args.k)


if __name__ == "__main__":
    main()
