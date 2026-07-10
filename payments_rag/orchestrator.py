"""Orchestrator — the answer flow of the RAG loop.

Pure orchestration: retrieve chunks -> build a grounded prompt -> ask the LLM
adapter for a structured {answer, citations} -> map the cited chunk ids back to
source+page so the answer is verifiable (ADR-0006). The LLM plumbing lives in
`adapters.llm`; retrieval in `retrieval.retriever`.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import psycopg

from payments_rag import config
from payments_rag.adapters import llm
from payments_rag.retrieval.retriever import RetrievedChunk, retrieve


@dataclass
class Citation:
    chunk_id: int
    source: str
    page: int | None
    text: str  # the passage itself, so the UI can show the evidence, not just a page ref


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation]
    retrieval_s: float = 0.0   # seconds spent embedding + searching
    generation_s: float = 0.0  # seconds spent in the LLM call
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0      # estimated LLM cost for this answer


def build_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    """Assemble the grounded prompt: instruction + question + tagged sources."""
    instruction = (
        "Answer the question using ONLY the sources below. "
        "If they do not contain the answer, say so. "
        "Cite the [chunk id] numbers you used."
    )
    sources = "\n\n".join(
        f"[chunk {c.id}] ({c.source} p{c.page})\n{c.text}" for c in chunks
    )
    return f"{instruction}\n\nQuestion: {question}\n\nSources:\n{sources}"


def answer(conn: psycopg.Connection, question: str, *, k: int = 5) -> AnswerResult:
    t0 = perf_counter()
    chunks = retrieve(conn, question, k=k)
    retrieval_s = perf_counter() - t0

    t1 = perf_counter()
    prompt = build_prompt(question, chunks)
    data, usage = llm.complete_json(prompt)
    generation_s = perf_counter() - t1

    by_id = {c.id: c for c in chunks}
    citations: list[Citation] = []
    seen: set[int] = set()
    for cid in data["citations"]:
        chunk = by_id.get(cid)
        if chunk is None or cid in seen:
            continue
        seen.add(cid)
        citations.append(
            Citation(chunk_id=cid, source=chunk.source, page=chunk.page, text=chunk.text)
        )
    cost_usd = (
        usage["input_tokens"] * config.LLM_INPUT_COST_PER_MTOK
        + usage["output_tokens"] * config.LLM_OUTPUT_COST_PER_MTOK
    ) / 1_000_000
    return AnswerResult(
        answer=data["answer"],
        citations=citations,
        retrieval_s=retrieval_s,
        generation_s=generation_s,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cost_usd=cost_usd,
    )
