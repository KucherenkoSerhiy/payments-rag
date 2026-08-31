"""Adapter: OpenAI's Responses API `file_search` tool.

The closest thing OpenAI ships to "RAG in a box": upload files, get a managed
vector store, ask questions, get citations back. See `docs/vs-managed-rag.md`
for why this is an empirical comparator only, not an integration candidate
(it creates a persistent OpenAI-hosted index of the corpus).

Field names below (`ResponseFileSearchToolCall.results`, `usage.input_tokens`,
`AnnotationFileCitation`) were confirmed by introspecting the installed SDK
(openai 2.41.1), not assumed from docs.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from openai import OpenAI

from comparison.logging_setup import get_logger
from comparison.schema import SystemAnswer
from payments_rag import config

log = get_logger("comparison.openai_filesearch")

MODEL = "gpt-4o"
INPUT_COST_PER_MTOK = 2.5    # gpt-4o list price, USD per 1M input tokens
OUTPUT_COST_PER_MTOK = 10.0  # gpt-4o list price, USD per 1M output tokens
FILE_SEARCH_COST_PER_1K_CALLS = 2.50  # USD; first 1GB/day storage is free, this corpus is well under it


def _client() -> OpenAI:
    return OpenAI(api_key=config.require_openai_key())


def setup_vector_store(pdf_paths: list[Path], name: str = "payments-rag-comparison") -> str:
    """One-time setup: upload the corpus PDFs, wait for indexing. Returns the vector store id."""
    client = _client()
    vs = client.vector_stores.create(name=name)
    log.info("created vector store %s (%s)", vs.id, name)
    for path in pdf_paths:
        with path.open("rb") as f:
            file_obj = client.files.create(file=f, purpose="assistants")
        client.vector_stores.files.create_and_poll(vector_store_id=vs.id, file_id=file_obj.id)
        log.info("indexed %s as file %s", path.name, file_obj.id)
    return vs.id


def answer(vector_store_id: str, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
    client = _client()
    t0 = perf_counter()
    resp = client.responses.create(
        model=MODEL,
        input=question,
        tools=[{"type": "file_search", "vector_store_ids": [vector_store_id]}],
        include=["file_search_call.results"],
    )
    latency_s = perf_counter() - t0

    answer_text = ""
    contexts: list[str] = []
    citations: list[str] = []
    for item in resp.output:
        if item.type == "file_search_call" and item.results:
            contexts.extend(r.text for r in item.results)
        if item.type == "message":
            for block in item.content:
                if block.type == "output_text":
                    answer_text += block.text
                    citations.extend(
                        f"{a.filename} (annotation idx {a.index})"
                        for a in block.annotations
                        if a.type == "file_citation"
                    )

    usage = resp.usage
    cost_usd = (
        usage.input_tokens * INPUT_COST_PER_MTOK + usage.output_tokens * OUTPUT_COST_PER_MTOK
    ) / 1_000_000 + FILE_SEARCH_COST_PER_1K_CALLS / 1000

    log.info(
        "%s: %.2fs, $%.5f, %d contexts, %d citations",
        question_id, latency_s, cost_usd, len(contexts), len(citations),
    )
    return SystemAnswer(
        system="openai-file-search",
        question_id=question_id,
        question=question,
        answer=answer_text,
        contexts=contexts,
        citations=citations,
        ground_truth=ground_truth,
        latency_s=latency_s,
        cost_usd=cost_usd,
        raw={"response_id": resp.id, "model": MODEL, "vector_store_id": vector_store_id},
    )
