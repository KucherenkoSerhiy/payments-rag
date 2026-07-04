"""Tests for the recall@k metric functions — your target to make green.

Run: uv run pytest tests/test_retrieval_eval.py
No DB or API needed — these check pure functions on plain data.
"""

from __future__ import annotations

from evals.retrieval_eval import hit_at_k, recall_at_k

# Retrieved (source, page) pairs, best-first: rank 1, 2, 3.
RETRIEVED = [("a.pdf", 1), ("a.pdf", 2), ("b.pdf", 9)]


def test_hit_when_expected_page_is_in_top_k() -> None:
    assert hit_at_k(RETRIEVED, {("a.pdf", 2)}, k=3) is True


def test_miss_when_expected_page_is_ranked_below_k() -> None:
    # ("b.pdf", 9) is rank 3, so with k=2 it must NOT count
    assert hit_at_k(RETRIEVED, {("b.pdf", 9)}, k=2) is False


def test_only_the_first_k_count() -> None:
    assert hit_at_k(RETRIEVED, {("a.pdf", 1)}, k=1) is True
    assert hit_at_k(RETRIEVED, {("a.pdf", 2)}, k=1) is False


def test_no_expected_pages_is_a_miss() -> None:
    assert hit_at_k(RETRIEVED, set(), k=3) is False


def test_hit_when_any_of_several_expected_is_in_top_k() -> None:
    # a question can have multiple valid answer pages; one hit in top-k is enough
    assert hit_at_k(RETRIEVED, {("z.pdf", 1), ("b.pdf", 9)}, k=3) is True


def test_recall_is_fraction_of_hits() -> None:
    assert recall_at_k([True, False, True, False]) == 0.5


def test_recall_all_hits() -> None:
    assert recall_at_k([True, True, True]) == 1.0


def test_recall_empty_is_zero() -> None:
    assert recall_at_k([]) == 0.0
