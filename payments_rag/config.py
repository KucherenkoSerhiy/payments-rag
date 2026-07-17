"""Central config. Reads .env once; every other module imports from here.

Keys are validated lazily (via the require_* functions), not at import, so a
DB-only script doesn't fail because an unrelated API key is missing.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()  # no-op if .env is absent; real env vars still win


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill it in, "
            f"or export {name} in your shell."
        )
    return value


# --- LLM (production responder) ---
# Haiku 4.5: cheapest current Claude ($1/$5 per 1M). Note: the eval judge must
# stay a different model (GPT-4) to preserve cross-model judging (scoping).
LLM_MODEL: str = os.environ.get("LLM_MODEL", "claude-haiku-4-5")
# Haiku 4.5 pricing (USD per 1M tokens), used to estimate per-query cost.
LLM_INPUT_COST_PER_MTOK: float = 1.0
LLM_OUTPUT_COST_PER_MTOK: float = 5.0

# Eval judge: a DIFFERENT model from LLM_MODEL, to keep cross-model judging
# (the producer must not grade its own homework, ADR-0007).
JUDGE_MODEL: str = os.environ.get("JUDGE_MODEL", "gpt-4o")


def require_anthropic_key() -> str:
    return _require("ANTHROPIC_API_KEY")


# --- Embeddings ---
# Pinned. Changing the model invalidates every stored vector (scoping risk #8).
EMBED_MODEL: str = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM: int = 1536  # dimension of text-embedding-3-small; must match init.sql


def require_openai_key() -> str:
    return _require("OPENAI_API_KEY")


# --- Vector store ---
# Use 127.0.0.1, not "localhost", in DATABASE_URL (.env/env): on Windows localhost
# resolves to IPv6 ::1 first, but the Docker port is IPv4-only, so a localhost
# connect hangs ~10s.
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "postgresql://payments:payments@127.0.0.1:5433/payments_rag"
)
DB_CONNECT_TIMEOUT: int = 10  # seconds; fail fast instead of hanging on a bad route

# --- Wallet guard (public deploy) ---
# Article 06: "anyone can run up the LLM bill from a for-loop". These bounds are
# enforced by api/guard.py on the paid endpoints. Days roll over at UTC midnight
# (the DB server's CURRENT_DATE).
DAILY_BUDGET_USD: float = float(os.environ.get("DAILY_BUDGET_USD", "0.30"))
RATE_LIMIT_ASK_PER_HOUR: int = int(os.environ.get("RATE_LIMIT_ASK_PER_HOUR", "20"))
RATE_LIMIT_EVALS_PER_HOUR: int = int(os.environ.get("RATE_LIMIT_EVALS_PER_HOUR", "6"))
MAX_QUESTION_CHARS: int = int(os.environ.get("MAX_QUESTION_CHARS", "500"))

# --- API resilience (both the LLM and embedding clients) ---
# The SDKs already retry 429/5xx with backoff; it's the default 10-minute timeout
# that lets a wedged connection hang for minutes. A short per-attempt timeout
# fails fast so the built-in retry can reconnect.
API_TIMEOUT: float = 60.0  # seconds per request attempt
API_MAX_RETRIES: int = 3
