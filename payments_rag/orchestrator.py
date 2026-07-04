"""Orchestrator — the answer half of the RAG loop (M3).

Ties retrieval to generation: retrieve chunks -> build a grounded prompt ->
ask the LLM for a structured {answer, citations} -> map the cited chunk ids
back to source+page so the answer is verifiable (ADR-0006).

TWO FUNCTIONS ARE LEFT FOR YOU: `build_prompt` and `answer`. The LLM call
(`_llm_json`) and the data types are provided. Guidance is in each stub.

Workflow:
    1. Implement build_prompt and answer below.
    2. uv run pytest tests/test_orchestrator.py     # until green
    3. uv run python -m payments_rag.cli ask "how fast does SCT Inst settle?"
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import psycopg
from anthropic import Anthropic

from payments_rag import config
from payments_rag.retriever import RetrievedChunk, retrieve  # noqa: F401  (retrieve: for answer())


@dataclass
class Citation:
    chunk_id: int
    source: str
    page: int | None


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation]


# The LLM must return exactly this shape; structured outputs guarantee it.
_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "integer"}},  # chunk ids used
    },
    "required": ["answer", "citations"],
    "additionalProperties": False,
}

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=config.require_anthropic_key())
    assert _client is not None
    return _client


def _llm_json(prompt: str) -> dict:
    """Call the LLM and return its {answer, citations} as a dict.

    Provided for you. Uses structured outputs, so the reply is always valid JSON
    matching _ANSWER_SCHEMA — no parsing surprises. You don't need to touch this.
    """
    resp = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _ANSWER_SCHEMA}},
    )
    text = next(block.text for block in resp.content if block.type == "text")
    return json.loads(text)


# ===========================================================================
# YOUR TASK — implement build_prompt() and answer().
# Tests: tests/test_orchestrator.py (build_prompt needs no API; answer is
# tested with _llm_json and retrieve monkeypatched, so no API/DB there either).
# ===========================================================================

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
    """Answer a question with citations. Orchestrate the whole flow:

      1. chunks = retrieve(conn, question, k=k)
      2. prompt = build_prompt(question, chunks)
      3. data   = _llm_json(prompt)          # {"answer": str, "citations": [int]}
      4. Map each cited id back to source+page: build a {chunk.id: chunk} lookup
         from `chunks`, then for each id in data["citations"] that IS in the
         lookup, make a Citation(id, source, page). Skip ids not in the lookup
         (the model can occasionally cite an id that wasn't retrieved).
      5. Return AnswerResult(answer=data["answer"], citations=[...]).
    """
    chunks = retrieve(conn, question, k=k)
    prompt = build_prompt(question, chunks)
    data = _llm_json(prompt)

    by_id = {c.id: c for c in chunks}
    citations: list[Citation] = []
    seen: set[int] = set()
    for cid in data["citations"]:      # keep the model's citation order
        chunk = by_id.get(cid)         # None if the model cited an id we didn't retrieve
        if chunk is None or cid in seen:
            continue
        seen.add(cid)
        citations.append(Citation(chunk_id=cid, source=chunk.source, page=chunk.page))
    return AnswerResult(answer=data["answer"], citations=citations)
