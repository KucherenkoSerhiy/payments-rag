"""The run loop every collector shares: golden set in, one JSONL row per answer out."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import perf_counter

import yaml

from comparison.logging_setup import get_logger
from comparison.schema import SystemAnswer, append_jsonl

_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN = _ROOT / "evals" / "answer_golden_set.yaml"
CORPUS = _ROOT / "corpus" / "raw"


def load_golden() -> list[dict]:
    """The 10 golden-set entries: {id, question, expected_answer} each."""
    return yaml.safe_load(GOLDEN.read_text(encoding="utf-8")) or []


def corpus_pdfs() -> list[Path]:
    pdfs = sorted(CORPUS.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"no corpus PDFs found in {CORPUS}")
    return pdfs


def collect(system: str, entries: list[dict], answer_one: Callable[[dict], SystemAnswer]) -> None:
    """Ask `answer_one` every entry, appending each row so a crash loses at most one."""
    log = get_logger(f"comparison.collect.{system}")
    out = Path(f"data/comparison/{system.replace('-', '_')}.jsonl")

    log.info("starting %s collection: %d questions", system, len(entries))
    out.unlink(missing_ok=True)  # fresh run each time, not appended to a stale file

    t0 = perf_counter()
    total_cost = 0.0
    for entry in entries:
        record = answer_one(entry)
        append_jsonl(out, record)
        total_cost += record.cost_usd
        log.info(
            "%s: %.2fs, $%.5f, %d contexts",
            record.question_id, record.latency_s, record.cost_usd, len(record.contexts),
        )

    log.info(
        "done: %d questions in %.1fs, total cost $%.4f, written to %s",
        len(entries), perf_counter() - t0, total_cost, out,
    )
