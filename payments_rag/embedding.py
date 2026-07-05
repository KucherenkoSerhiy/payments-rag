"""Embedding model wrapper — the keystone shared by indexing and query.

Same model, same call site for both paths, or vectors are not comparable
(scoping: the Embedding Model is the shared keystone).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from openai import OpenAI

from payments_rag import config

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.require_openai_key(),
            timeout=config.API_TIMEOUT,
            max_retries=config.API_MAX_RETRIES,
        )
    assert _client is not None
    return _client


def embed(texts: Sequence[str]) -> list[list[float]]:
    """Embed a batch of texts with the pinned model. Order is preserved."""
    if not texts:
        return []
    resp = _get_client().embeddings.create(model=config.EMBED_MODEL, input=list(texts))
    return [d.embedding for d in resp.data]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
