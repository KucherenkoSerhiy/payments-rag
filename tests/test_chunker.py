"""Unit tests for the sentence-aware chunker: deterministic, no API/DB."""

from __future__ import annotations

import pytest

from payments_rag.indexing.chunker import chunk_text, split_sentences

# 10 sentences, ~6 words each.
SENTENCES = [f"This is sentence number {i} here." for i in range(10)]
TEXT = " ".join(SENTENCES)


def test_empty_input_returns_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_split_sentences_basic() -> None:
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]


def test_short_text_is_a_single_chunk() -> None:
    assert chunk_text("Alpha beta gamma.", size=300, overlap=50) == ["Alpha beta gamma."]


def test_chunks_are_whole_sentences() -> None:
    # every chunk should end at a sentence boundary
    chunks = chunk_text(TEXT, size=18, overlap=6)
    assert len(chunks) > 1
    assert all(c.rstrip().endswith((".", "!", "?")) for c in chunks)


def test_no_chunk_greatly_exceeds_size() -> None:
    # a chunk may overshoot by at most the last sentence added
    chunks = chunk_text(TEXT, size=18, overlap=6)
    longest_sentence = max(len(s.split()) for s in SENTENCES)
    assert all(len(c.split()) <= 18 + longest_sentence for c in chunks)


def test_consecutive_chunks_overlap() -> None:
    chunks = chunk_text(TEXT, size=18, overlap=6)
    # the start of chunk k+1 should repeat a trailing sentence of chunk k
    for a, b in zip(chunks, chunks[1:]):
        a_sents = split_sentences(a)
        b_sents = split_sentences(b)
        assert b_sents[0] in a_sents


def test_zero_overlap_has_no_repeats() -> None:
    chunks = chunk_text(TEXT, size=18, overlap=0)
    seen: list[str] = []
    for c in chunks:
        seen.extend(split_sentences(c))
    assert len(seen) == len(set(seen)) == len(SENTENCES)


def test_oversize_sentence_becomes_its_own_chunk() -> None:
    big = "word " * 50  # 50-word single "sentence" (no terminator)
    chunks = chunk_text(big.strip() + ".", size=10, overlap=2)
    assert len(chunks) == 1  # can't split inside a sentence


@pytest.mark.parametrize("bad", [0, -1])
def test_rejects_non_positive_size(bad: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c.", size=bad)


@pytest.mark.parametrize("overlap", [-1, 300, 400])
def test_rejects_invalid_overlap(overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c.", size=300, overlap=overlap)
