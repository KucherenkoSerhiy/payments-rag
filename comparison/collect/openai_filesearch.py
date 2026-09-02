"""Collect OpenAI file_search's answers. Uploads the corpus to a fresh
OpenAI-managed vector store first - a persistent third-party copy of the corpus,
which is why this stays a comparison-only adapter (docs/vs-managed-rag.md).
Real cost, ~$0.35/run:

    PYTHONIOENCODING=utf-8 PYTHONPATH=. python -m comparison.collect.openai_filesearch
"""

from __future__ import annotations

from dotenv import load_dotenv

from comparison.adapters.openai_filesearch_adapter import OpenAIFileSearchIndexer, OpenAIFileSearchRag
from comparison.collect.base import collect, corpus_pdfs, load_golden

load_dotenv()


def run() -> None:
    vector_store_id = OpenAIFileSearchIndexer().upload_corpus(corpus_pdfs())
    rag = OpenAIFileSearchRag(vector_store_id)
    collect(
        "openai-file-search",
        load_golden(),
        lambda e: rag.answer(e["id"], e["question"], e["expected_answer"]),
    )


if __name__ == "__main__":
    run()
