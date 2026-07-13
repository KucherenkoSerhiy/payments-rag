"""Tests for the answer-eval aggregation: your target. Pure, no I/O."""

from __future__ import annotations

import pytest

from evals.answer_eval import summarize


def test_mean_and_pass_rate() -> None:
    mean, rate = summarize([100, 80, 60], threshold=70)
    assert mean == pytest.approx(80.0)
    assert rate == pytest.approx(2 / 3)  # 100 and 80 pass, 60 fails


def test_all_below_threshold() -> None:
    mean, rate = summarize([50, 50], threshold=70)
    assert mean == pytest.approx(50.0)
    assert rate == 0.0


def test_threshold_is_inclusive() -> None:
    # a score exactly at the threshold counts as a pass
    mean, rate = summarize([70, 90], threshold=70)
    assert mean == pytest.approx(80.0)
    assert rate == pytest.approx(1.0)


def test_empty_is_zero() -> None:
    assert summarize([]) == (0.0, 0.0)
