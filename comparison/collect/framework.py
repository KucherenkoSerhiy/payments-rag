"""Collect answers from one framework-built RAG pipeline. The adapter module is
imported lazily because each framework runs in its own `uv --isolated` environment
(Makefile compare-* targets, docs/adr/0019):

    PYTHONPATH=. PYTHONIOENCODING=utf-8 uv run --isolated --with <framework deps> \\
        python -m comparison.collect.framework {haystack|llamaindex|langchain}
"""

from __future__ import annotations

import argparse
import importlib

from dotenv import load_dotenv

from comparison.collect.base import collect, corpus_pdfs, load_golden

load_dotenv()

FRAMEWORKS = {
    "haystack": "comparison.adapters.haystack_adapter",
    "llamaindex": "comparison.adapters.llamaindex_adapter",
    "langchain": "comparison.adapters.langchain_adapter",
}


def run(name: str) -> None:
    rag = importlib.import_module(FRAMEWORKS[name]).build(corpus_pdfs())
    collect(
        name,
        load_golden(),
        lambda e: rag.answer(e["id"], e["question"], e["expected_answer"]),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="comparison.collect.framework")
    parser.add_argument("framework", choices=sorted(FRAMEWORKS))
    run(parser.parse_args(argv).framework)


if __name__ == "__main__":
    main()
