"""Unified provider clients for the model matrix: embed(texts) and chat(prompt).

Deliberately protocol-thin so the whole 5-vendor matrix runs on dependencies
the project already has (ADR-0004: no new frameworks, and nothing new in
pyproject.toml):

  * OpenAI, DeepSeek and Gemini all speak the OpenAI chat/embeddings protocol -
    DeepSeek natively, Gemini via its OpenAI-compatibility endpoint - so one
    `openai` SDK client per base_url covers three vendors.
  * Anthropic uses its own SDK (already a production dependency).
  * Voyage has no OpenAI-compatible endpoint; its REST API is one POST, called
    with `httpx` (already present transitively).

Usage tokens are captured on every call so cost is computed from config price
constants, never estimated from word counts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from anthropic import Anthropic
from openai import OpenAI

from comparison.matrix.config import PROVIDER_ENV_KEYS, ChatModel, EmbedModel

_OPENAI_COMPAT_BASE_URLS = {
    "openai": None,  # SDK default
    "deepseek": "https://api.deepseek.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}

_MAX_ANSWER_TOKENS = 1024


class MissingKeyError(RuntimeError):
    """Raised when a provider's API key env var is absent - a setup blocker."""


def _api_key(provider: str) -> str:
    env = PROVIDER_ENV_KEYS[provider]
    key = os.environ.get(env, "").strip()
    if not key:
        raise MissingKeyError(f"{env} not set (needed for provider '{provider}')")
    return key


_openai_clients: dict[str, OpenAI] = {}
_anthropic_client: Anthropic | None = None


def _openai_compat(provider: str) -> OpenAI:
    if provider not in _openai_clients:
        _openai_clients[provider] = OpenAI(
            api_key=_api_key(provider),
            base_url=_OPENAI_COMPAT_BASE_URLS[provider],
            timeout=120,
            max_retries=3,
        )
    return _openai_clients[provider]


def _anthropic() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic(api_key=_api_key("anthropic"), timeout=120, max_retries=3)
    return _anthropic_client


# --- embeddings ---------------------------------------------------------------

def embed(model: EmbedModel, texts: list[str]) -> tuple[list[list[float]], int]:
    """Embed a batch of texts; returns (vectors, input_tokens_used)."""
    if model.provider == "voyage":
        return _embed_voyage(model, texts)
    resp = _openai_compat(model.provider).embeddings.create(model=model.model_id, input=texts)
    vectors = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
    tokens = resp.usage.prompt_tokens if resp.usage else 0
    return vectors, tokens


def _embed_voyage(model: EmbedModel, texts: list[str]) -> tuple[list[list[float]], int]:
    r = httpx.post(
        "https://api.voyageai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {_api_key('voyage')}"},
        json={"model": model.model_id, "input": texts},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    vectors = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
    return vectors, int(data.get("usage", {}).get("total_tokens", 0))


# --- chat --------------------------------------------------------------------

@dataclass(frozen=True)
class ChatResult:
    text: str
    input_tokens: int
    output_tokens: int


def chat(model: ChatModel, prompt: str) -> ChatResult:
    """One user-turn completion; same call shape for every vendor."""
    if model.provider == "anthropic":
        resp = _anthropic().messages.create(
            model=model.model_id,
            max_tokens=_MAX_ANSWER_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return ChatResult(text, resp.usage.input_tokens, resp.usage.output_tokens)

    resp = _openai_compat(model.provider).chat.completions.create(
        model=model.model_id,
        max_completion_tokens=_MAX_ANSWER_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = resp.usage
    return ChatResult(
        resp.choices[0].message.content or "",
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )


def chat_cost_usd(model: ChatModel, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * model.price_in_per_mtok + output_tokens * model.price_out_per_mtok
    ) / 1_000_000


def embed_cost_usd(model: EmbedModel, tokens: int) -> float:
    return tokens * model.price_per_mtok / 1_000_000
