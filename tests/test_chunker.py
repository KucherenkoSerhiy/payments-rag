"""Unit test for the chunker — deterministic, no API calls (runs in <1s)."""

from __future__ import annotations

import pytest

from payments_rag.chunker import chunk_text


def test_empty_input_returns_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_is_a_single_chunk() -> None:
    chunks = chunk_text("alpha beta gamma", size=300, overlap=50)
    assert chunks == ["alpha beta gamma"]


def test_splits_into_expected_count_with_overlap() -> None:
    words = [f"w{i}" for i in range(1000)]
    chunks = chunk_text(" ".join(words), size=300, overlap=50)
    # step = 250 -> windows start at 0,250,500,750 -> 4 chunks
    assert len(chunks) == 4
    assert chunks[0].split()[0] == "w0"
    assert chunks[-1].split()[-1] == "w999"


def test_consecutive_chunks_share_overlap_words() -> None:
    words = [f"w{i}" for i in range(700)]
    chunks = chunk_text(" ".join(words), size=300, overlap=50)
    first = chunks[0].split()
    second = chunks[1].split()
    # last 50 of chunk 0 == first 50 of chunk 1
    assert first[-50:] == second[:50]


def test_no_window_exceeds_size() -> None:
    words = [f"w{i}" for i in range(950)]
    chunks = chunk_text(" ".join(words), size=300, overlap=50)
    assert all(len(c.split()) <= 300 for c in chunks)


@pytest.mark.parametrize("bad", [0, -1])
def test_rejects_non_positive_size(bad: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c", size=bad)


@pytest.mark.parametrize("overlap", [-1, 300, 400])
def test_rejects_invalid_overlap(overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c", size=300, overlap=overlap)
