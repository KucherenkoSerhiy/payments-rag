"""Judge: grade a produced answer against a reference (cross-model).

Uses a DIFFERENT model from the production responder (GPT-4 vs Claude) so it
doesn't mark its own homework (ADR-0007). Eval-only, so it lives in `evals/`,
not in the production `adapters/`. Structured output guarantees a clean
{score, critique}.
"""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from payments_rag import config

logger = logging.getLogger(__name__)

# gpt-4o list prices, USD per 1M tokens - same figures the comparison adapters use.
INPUT_COST_PER_MTOK = 2.5
OUTPUT_COST_PER_MTOK = 10.0

_GRADE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},  # 0-100: factual match to the reference
        "critique": {"type": "string"},  # one sentence
    },
    "required": ["score", "critique"],
    "additionalProperties": False,
}

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


def _build_prompt(question: str, expected: str, actual: str) -> str:
    return (
        "You are grading an answer to a payments-spec question for FACTUAL "
        "correctness against a reference answer. Score 0-100: 100 = fully correct "
        "and complete vs the reference; 0 = wrong or missing the key fact. Ignore "
        "wording and style; judge the facts. Give a one-sentence critique.\n\n"
        f"QUESTION: {question}\n"
        f"REFERENCE: {expected}\n"
        f"CANDIDATE: {actual}\n"
    )


def judge(question: str, expected: str, actual: str) -> tuple[int, str]:
    """Grade `actual` against `expected`; return (score 0-100, one-line critique)."""
    resp = _get_client().chat.completions.create(
        model=config.JUDGE_MODEL,
        messages=[{"role": "user", "content": _build_prompt(question, expected, actual)}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "grade", "strict": True, "schema": _GRADE_SCHEMA},
        },
    )
    data = json.loads(resp.choices[0].message.content)
    if resp.usage:
        logger.info(
            "judge call: %d in / %d out tokens, ~$%.5f",
            resp.usage.prompt_tokens,
            resp.usage.completion_tokens,
            judge_cost_usd(resp.usage.prompt_tokens, resp.usage.completion_tokens),
        )
    return int(data["score"]), data["critique"]


def judge_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens * INPUT_COST_PER_MTOK + completion_tokens * OUTPUT_COST_PER_MTOK) / 1_000_000
