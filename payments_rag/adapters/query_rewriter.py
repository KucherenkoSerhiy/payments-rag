"""Query rewriter adapter: one casual question -> a few spec-vocabulary rephrasings.

Powers multi-query retrieval (retrieval/multi_query.py, ADR-0022). Uses the
production Claude model (Haiku-class, ~$0.0001/question); the *retrieval* still
only ever sees real corpus text, so unlike HyDE nothing hallucinated can enter
the index or the prompt.
"""

from __future__ import annotations

import logging

from anthropic import Anthropic

from payments_rag import config

logger = logging.getLogger(__name__)

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


def _build_prompt(question: str, n: int) -> str:
    return (
        f"Rewrite this question about SEPA payment schemes into {n} alternative "
        "phrasings for searching the official EPC rulebooks. Use the formal "
        "vocabulary a rulebook would use (e.g. 'maximum execution time', "
        "'Originator PSP', 'settlement') where the question is casual. Keep each "
        "a single short question or noun phrase. Do not answer the question. "
        f"Output exactly {n} lines, one rewrite per line, no numbering.\n\n"
        f"QUESTION: {question}\n"
    )


def rewrite(question: str, *, n: int = 3) -> list[str]:
    """Return up to `n` rephrasings of `question` (the original is not included)."""
    resp = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=300,
        temperature=0.0,  # rewrites must be stable or recall@k becomes a dice roll
        messages=[{"role": "user", "content": _build_prompt(question, n)}],
    )
    lines = [line.strip(" -*\t") for line in resp.content[0].text.splitlines()]
    variants = [line for line in lines if line and line.lower() != question.lower()]
    return variants[:n]
