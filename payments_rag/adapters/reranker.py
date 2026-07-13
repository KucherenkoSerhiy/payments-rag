"""Reranker adapter: score how relevant one passage is to a question.

A cross-encoder-style reranker. The bi-encoder (embedding.py) embeds the question
and the passage *separately*, so the whole corpus can be indexed ahead of time:
fast, but it never compares the two directly. This shows the model BOTH together
and asks for a single relevance score, sharper, but one API call per
(question, passage) pair, so it only ever runs over a small fanout of candidates.

We instantiate the cross-encoder as an LLM call rather than a local model
(sentence-transformers / BGE), to avoid a heavy ML stack. The cost of that choice
is LATENCY: one sequential API call per candidate makes a full fanout take ~1
minute per query. So this is EVAL-ONLY (retrieval_eval --rerank) and deliberately
NOT in the interactive answer path. A production reranker would be a local
cross-encoder that scores all candidates in one batched pass in tens of ms. See
ADR-0016. Relevance scoring isn't self-marking, so reusing Haiku is fine here.
"""

from __future__ import annotations

import json

from anthropic import Anthropic

from payments_rag import config


def relevance(question: str, passage: str) -> int:
    """Score how well `passage` answers `question`: 0 (unrelated) to 100 (direct)."""
    resp = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": _build_prompt(question, passage)}],
        output_config={"format": {"type": "json_schema", "schema": _SCORE_SCHEMA}},
    )
    text = next(block.text for block in resp.content if block.type == "text")
    return int(json.loads(text)["relevance"])


def _build_prompt(question: str, passage: str) -> str:
    return (
        "Score how well the PASSAGE answers the QUESTION, from 0 to 100: "
        "100 = the passage directly and fully answers it; 0 = unrelated. Judge "
        "only whether the answer is present, not the wording.\n\n"
        f"QUESTION: {question}\n"
        f"PASSAGE: {passage}\n"
    )


_SCORE_SCHEMA = {
    "type": "object",
    "properties": {"relevance": {"type": "integer"}},  # 0-100
    "required": ["relevance"],
    "additionalProperties": False,
}

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(
            api_key=config.require_anthropic_key(),
            timeout=config.API_TIMEOUT,
            max_retries=config.API_MAX_RETRIES,
        )
    assert _client is not None
    return _client
