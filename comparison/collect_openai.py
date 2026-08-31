"""Collect OpenAI file_search's answers over the golden set.

Uploads the two corpus PDFs to a fresh OpenAI-managed vector store once, then
asks every golden-set question against it. Costs roughly $0.03 total for the
10-question run (see docs/vs-managed-rag.md for why this stays a comparison-only
adapter, never an integration target: the vector store is a persistent
third-party copy of the corpus).

    PYTHONIOENCODING=utf-8 PYTHONPATH=. python -m comparison.collect_openai
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import yaml

from comparison.adapters import openai_filesearch_adapter as ofs
from comparison.logging_setup import get_logger
from comparison.schema import append_jsonl

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "answer_golden_set.yaml"
CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "raw"
PDFS = [CORPUS / "sct_rulebook_2025.pdf", CORPUS / "sct_inst_rulebook_2025.pdf"]
OUT = Path("data/comparison/openai_file_search.jsonl")

log = get_logger("comparison.collect_openai")


def run() -> None:
    entries = yaml.safe_load(GOLDEN.read_text(encoding="utf-8")) or []
    log.info("starting OpenAI file_search collection: %d questions", len(entries))
    OUT.unlink(missing_ok=True)

    missing = [p for p in PDFS if not p.exists()]
    if missing:
        raise FileNotFoundError(f"corpus PDFs not found: {missing}. Run `make index` prerequisites first.")

    t0 = perf_counter()
    vs_id = ofs.setup_vector_store(PDFS)
    log.info("vector store ready: %s", vs_id)

    total_cost = 0.0
    for entry in entries:
        record = ofs.answer(vs_id, entry["id"], entry["question"], entry["expected_answer"])
        append_jsonl(OUT, record)
        total_cost += record.cost_usd

    log.info(
        "done: %d questions in %.1fs, total cost $%.4f, written to %s",
        len(entries), perf_counter() - t0, total_cost, OUT,
    )


if __name__ == "__main__":
    run()
