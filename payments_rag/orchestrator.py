"""Orchestrator — the answer flow of the RAG loop.

Pure orchestration: retrieve chunks -> build a grounded prompt -> ask the LLM
adapter for a structured {answer, citations} -> map the cited chunk ids back to
source+page so the answer is verifiable (ADR-0006). The LLM plumbing lives in
`adapters.llm`; retrieval in `retrieval.retriever`.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from payments_rag.adapters import llm
from payments_rag.retrieval.retriever import RetrievedChunk, retrieve


@dataclass
class Citation:
    chunk_id: int
    source: str
    page: int | None


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation]


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
    chunks = retrieve(conn, question, k=k)
    prompt = build_prompt(question, chunks)
    data = llm.complete_json(prompt)

    by_id = {c.id: c for c in chunks}
    citations: list[Citation] = []
    seen: set[int] = set()
    for cid in data["citations"]:
        chunk = by_id.get(cid)
        if chunk is None or cid in seen:
            continue
        seen.add(cid)
        citations.append(Citation(chunk_id=cid, source=chunk.source, page=chunk.page))
    return AnswerResult(answer=data["answer"], citations=citations)
