"""Unit tests for the model-matrix experiment harness (comparison/matrix).

All offline: no API calls, no network. Provider clients are exercised only
through their pure helpers (cost math, reply parsing); retrieval and chunking
run on synthetic corpora in tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from comparison.matrix import corpus as corpus_mod
from comparison.matrix.config import (
    CHAT_MODELS,
    EMBED_MODELS,
    JUDGES,
    PIPELINES,
    TOPICS,
)
from comparison.matrix.judge_matrix import _parse_grade
from comparison.matrix.providers import chat_cost_usd, embed_cost_usd
from comparison.matrix.store import VectorStore
from comparison.matrix.corpus import Chunk

GOLDEN_DIR = Path("comparison/matrix/golden")


# --- config sanity -----------------------------------------------------------

def test_pipelines_reference_known_models():
    for pipe in PIPELINES:
        assert pipe.embed in EMBED_MODELS, pipe.key
        assert pipe.chat in CHAT_MODELS, pipe.key


def test_judges_reference_known_models():
    for judge in JUDGES:
        assert judge in CHAT_MODELS


def test_judges_cover_three_vendor_families():
    providers = {CHAT_MODELS[j].provider for j in JUDGES}
    assert len(providers) == 3, "self-preference measurement needs one judge per family"


def test_every_pipeline_differs_by_one_component_from_some_other():
    """Single-variable design guarantee - except pipelines explicitly flagged
    cross_stack (whole-stack comparisons; exactly one is allowed)."""
    cross_stack = [p for p in PIPELINES if p.cross_stack]
    assert len(cross_stack) == 1
    for pipe in PIPELINES:
        if pipe.cross_stack:
            continue
        neighbours = [
            other for other in PIPELINES
            if other.key != pipe.key
            and (other.embed == pipe.embed) != (other.chat == pipe.chat)
        ]
        assert neighbours, f"{pipe.key} has no single-variable comparison partner"


# --- golden sets -------------------------------------------------------------

@pytest.mark.parametrize("topic", TOPICS)
def test_golden_set_shape(topic):
    entries = yaml.safe_load((GOLDEN_DIR / f"{topic}.yaml").read_text(encoding="utf-8"))
    assert len(entries) == 20, f"{topic}: expected 20 questions, got {len(entries)}"
    ids = [e["id"] for e in entries]
    assert len(set(ids)) == len(ids), f"{topic}: duplicate question ids"
    for e in entries:
        assert e["question"].strip().endswith("?"), e["id"]
        # Legacy answers can be legitimately terse ("Euro."), so only guard
        # against empty/placeholder values.
        assert len(e["expected_answer"].strip()) > 3, e["id"]


def test_sepa_golden_keeps_article05_overlap_verbatim():
    """The first 10 SEPA entries must stay identical to the article-05 set so
    results remain comparable across the two experiments."""
    legacy = yaml.safe_load(
        Path("evals/answer_golden_set.yaml").read_text(encoding="utf-8")
    )
    matrix = yaml.safe_load((GOLDEN_DIR / "sepa.yaml").read_text(encoding="utf-8"))
    legacy_by_id = {e["id"]: e for e in legacy}
    overlap = [e for e in matrix if e["id"] in legacy_by_id]
    assert len(overlap) == len(legacy), "some legacy SEPA questions are missing"
    for e in overlap:
        assert e["question"] == legacy_by_id[e["id"]]["question"]
        assert e["expected_answer"] == legacy_by_id[e["id"]]["expected_answer"]


# --- chunking ----------------------------------------------------------------

def test_chunking_windows_and_overlap(tmp_path, monkeypatch):
    words = [f"w{i}" for i in range(450)]
    topic_dir = tmp_path / "toy"
    topic_dir.mkdir()
    (topic_dir / "doc.txt").write_text(" ".join(words), encoding="utf-8")
    monkeypatch.setattr(corpus_mod, "TOPICS_DIR", tmp_path)

    chunks = corpus_mod.load_chunks("toy")
    assert all(c.source == "doc.txt" for c in chunks)
    first, second = chunks[0].text.split(), chunks[1].text.split()
    assert len(first) == 200
    assert first[-20:] == second[:20], "consecutive chunks must overlap by 20 words"
    joined = set()
    for c in chunks:
        joined.update(c.text.split())
    assert joined == set(words), "no word may be lost by chunking"


def test_fingerprint_tracks_content(tmp_path, monkeypatch):
    topic_dir = tmp_path / "toy"
    topic_dir.mkdir()
    doc = topic_dir / "doc.txt"
    doc.write_text("hello corpus", encoding="utf-8")
    monkeypatch.setattr(corpus_mod, "TOPICS_DIR", tmp_path)

    before = corpus_mod.fingerprint("toy")
    doc.write_text("hello changed corpus", encoding="utf-8")
    assert corpus_mod.fingerprint("toy") != before


# --- vector store ------------------------------------------------------------

def test_store_ranks_by_cosine():
    store = VectorStore()
    store.add(
        [Chunk("a.txt", "aligned"), Chunk("b.txt", "orthogonal"), Chunk("c.txt", "opposite")],
        [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]],
    )
    hits = store.search([1.0, 0.0], k=3)
    assert [h[0].source for h in hits] == ["a.txt", "b.txt", "c.txt"]
    assert hits[0][1] == pytest.approx(1.0)
    assert hits[2][1] == pytest.approx(-1.0)


def test_store_search_empty_and_k_cap():
    store = VectorStore()
    assert store.search([1.0], k=5) == []
    store.add([Chunk("a.txt", "x")], [[1.0]])
    assert len(store.search([1.0], k=5)) == 1


# --- judge reply parsing -----------------------------------------------------

@pytest.mark.parametrize("reply", [
    '{"score": 85, "critique": "close enough"}',
    '```json\n{"score": 85, "critique": "close enough"}\n```',
    'Sure! Here is my grade: {"score": 85, "critique": "close enough"} Hope it helps.',
])
def test_parse_grade_tolerates_wrapping(reply):
    score, critique = _parse_grade(reply)
    assert score == 85
    assert critique == "close enough"


def test_parse_grade_rejects_no_json():
    with pytest.raises(ValueError):
        _parse_grade("I would rate this an 85 out of 100.")


# --- cost math ---------------------------------------------------------------

def test_cost_math():
    sonnet = CHAT_MODELS["sonnet"]
    assert chat_cost_usd(sonnet, 1_000_000, 0) == pytest.approx(sonnet.price_in_per_mtok)
    assert chat_cost_usd(sonnet, 0, 1_000_000) == pytest.approx(sonnet.price_out_per_mtok)
    emb = EMBED_MODELS["oai-small"]
    assert embed_cost_usd(emb, 1_000_000) == pytest.approx(emb.price_per_mtok)
