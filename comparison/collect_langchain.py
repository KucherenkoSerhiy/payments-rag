"""Collect answers from the LangChain/LangGraph-built RAG pipeline over the golden set.

Indexes the corpus PDFs in-memory once, then asks every golden-set question. See
docs/adr/0019 for why this comparator exists and why it runs isolated.

    PYTHONPATH=. PYTHONIOENCODING=utf-8 \\
        uv run --isolated --with langgraph --with langchain-openai \\
        --with langchain-text-splitters --with pypdf --with tiktoken \\
        --with python-dotenv --with pyyaml \\
        python -m comparison.collect_langchain
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import yaml
from dotenv import load_dotenv

from comparison.adapters import langchain_adapter as lc
from comparison.logging_setup import get_logger
from comparison.schema import append_jsonl

load_dotenv()

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "answer_golden_set.yaml"
CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "raw"
PDFS = sorted(CORPUS.glob("*.pdf"))
OUT = Path("data/comparison/langchain.jsonl")

log = get_logger("comparison.collect_langchain")


def run() -> None:
    entries = yaml.safe_load(GOLDEN.read_text(encoding="utf-8")) or []
    log.info("starting LangChain/LangGraph collection: %d questions, %d corpus PDFs", len(entries), len(PDFS))
    OUT.unlink(missing_ok=True)

    if not PDFS:
        raise FileNotFoundError(f"no corpus PDFs found in {CORPUS}")

    t0 = perf_counter()
    index = lc.index_corpus(PDFS)

    total_cost = 0.0
    for entry in entries:
        record = lc.answer(index, entry["id"], entry["question"], entry["expected_answer"])
        append_jsonl(OUT, record)
        total_cost += record.cost_usd

    log.info(
        "done: %d questions in %.1fs, total cost $%.4f, written to %s",
        len(entries), perf_counter() - t0, total_cost, OUT,
    )


if __name__ == "__main__":
    run()
