"""LLM adapter — call Claude and get a structured {answer, citations} back.

Mirrors `embedding.py` (the OpenAI adapter): module-level functions with a lazy
client singleton. Kept a module, not a class, per the Pythonic default at this
scale (ADR-0015); promote to a class + Protocol only if a second provider or
DI-based testing is ever needed.
"""

from __future__ import annotations

import json

from anthropic import Anthropic

from payments_rag import config

# The LLM must return exactly this shape; structured outputs guarantee it.
ANSWER_SCHEMA = {
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
        _client = Anthropic(
            api_key=config.require_anthropic_key(),
            timeout=config.API_TIMEOUT,
            max_retries=config.API_MAX_RETRIES,
        )
    assert _client is not None
    return _client


def complete_json(prompt: str) -> tuple[dict, dict]:
    """Call the LLM; return (parsed {answer, citations}, token usage).

    Structured outputs guarantee valid JSON matching ANSWER_SCHEMA. `usage` is
    {input_tokens, output_tokens}, used to estimate the query's cost.
    """
    resp = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
    )
    text = next(block.text for block in resp.content if block.type == "text")
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return json.loads(text), usage


def draft(prompt: str, *, max_tokens: int = 256) -> str:
    """Plain-text completion (no schema). Used for HyDE's hypothetical answers."""
    resp = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(block.text for block in resp.content if block.type == "text")
