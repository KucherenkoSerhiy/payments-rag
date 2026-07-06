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


def complete_json(prompt: str) -> dict:
    """Call the LLM and return its {answer, citations} as a dict.

    Uses structured outputs, so the reply is always valid JSON matching
    ANSWER_SCHEMA — no parsing surprises.
    """
    resp = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
    )
    text = next(block.text for block in resp.content if block.type == "text")
    return json.loads(text)
