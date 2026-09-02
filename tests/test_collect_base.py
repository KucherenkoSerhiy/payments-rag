"""Tests for the shared collection loop: rows appended per entry, fresh file per run."""

from __future__ import annotations

import json
from pathlib import Path

from comparison.collect.base import collect, load_golden
from comparison.schema import SystemAnswer

ENTRIES = [
    {"id": "q1", "question": "one?", "expected_answer": "1"},
    {"id": "q2", "question": "two?", "expected_answer": "2"},
]


def _answer(entry: dict) -> SystemAnswer:
    return SystemAnswer(
        system="fake-sys",
        question_id=entry["id"],
        question=entry["question"],
        answer=entry["expected_answer"],
        contexts=["ctx"],
        citations=[],
        ground_truth=entry["expected_answer"],
        latency_s=0.1,
        cost_usd=0.001,
    )


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_collect_writes_one_row_per_entry_in_order(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    collect("fake-sys", ENTRIES, _answer)
    rows = _read(tmp_path / "data" / "comparison" / "fake_sys.jsonl")
    assert [r["question_id"] for r in rows] == ["q1", "q2"]
    assert rows[0]["system"] == "fake-sys"


def test_collect_replaces_a_stale_file_not_appends(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "data" / "comparison" / "fake_sys.jsonl"
    out.parent.mkdir(parents=True)
    out.write_text('{"stale": true}\n', encoding="utf-8")
    collect("fake-sys", ENTRIES, _answer)
    assert len(_read(out)) == 2  # stale row gone, not 3


def test_load_golden_has_the_fields_every_collector_relies_on() -> None:
    entries = load_golden()
    assert len(entries) == 10
    assert all({"id", "question", "expected_answer"} <= e.keys() for e in entries)
