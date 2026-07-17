"""Wallet guard for the public deploy: rate limit + global daily budget cap.

Article 06: "anyone can run up the LLM bill from a for-loop" - this module is
what prevents that. The app is public and has no accounts (a deliberate deploy
choice, see ADR-0018), so the guards work without knowing who anyone is:

- Per-IP sliding-window rate limits on the paid endpoints. In-memory on
  purpose: state resets on restart, which under-counts briefly, and the budget
  cap below is the durable backstop.
- A global daily budget cap on paid API spend, persisted in the wallet_guard
  table so it survives restarts and redeploys. Once the day's spend reaches
  DAILY_BUDGET_USD every paid endpoint returns 429 until UTC midnight.
- Question length is bounded on the request model (api.main.AskRequest).

Spend accounting: /ask records the measured LLM cost from the orchestrator.
The eval and health endpoints make paid calls whose exact cost isn't measured
(embeddings, 1-token pings), so they charge flat, deliberately-high estimates.
Knobs live in payments_rag.config: DAILY_BUDGET_USD, RATE_LIMIT_ASK_PER_HOUR,
RATE_LIMIT_EVALS_PER_HOUR, MAX_QUESTION_CHARS.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque

import psycopg
from fastapi import HTTPException, Request

from payments_rag import config

logger = logging.getLogger(__name__)

BUDGET_MESSAGE = (
    "The demo hit its daily API budget, so paid calls are paused to protect "
    "the owner's wallet. It resets at midnight UTC - come back tomorrow."
)
RATE_MESSAGE = "Rate limit reached for this endpoint. Try again in a bit."

# Flat spend estimates for paid endpoints that don't measure their own cost.
# Deliberately high so the cap trips early rather than late.
EVAL_RUN_EST_USD = 0.002  # one embedding per golden-set question
HEALTH_RUN_EST_USD = 0.001  # two 1-token LLM pings + one embedding


def client_ip(request: Request) -> str:
    """Best-effort client address: Fly's header, then the proxy chain, then the peer."""
    for header in ("fly-client-ip", "x-forwarded-for"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window per-IP counter. `clock` is injectable for tests."""

    def __init__(self, limit: int, window_s: int = 3600, clock=time.monotonic) -> None:
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def retry_after(self, ip: str) -> int | None:
        """Count a hit and return None, or seconds to wait if the ip is over the limit."""
        now = self._clock()
        with self._lock:
            hits = self._hits[ip]
            while hits and now - hits[0] > self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, int(self.window_s - (now - hits[0])) + 1)
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory against IP churn
                stale = [k for k, v in self._hits.items() if not v or now - v[-1] > self.window_s]
                for key in stale:
                    del self._hits[key]
            return None


ask_limiter = RateLimiter(config.RATE_LIMIT_ASK_PER_HOUR)
evals_limiter = RateLimiter(config.RATE_LIMIT_EVALS_PER_HOUR)


def _enforce(limiter: RateLimiter, request: Request) -> None:
    wait = limiter.retry_after(client_ip(request))
    if wait is not None:
        logger.info("rate limit hit: %s %s", request.url.path, client_ip(request))
        raise HTTPException(429, RATE_MESSAGE, headers={"Retry-After": str(wait)})


def rate_limit_ask(request: Request) -> None:
    """FastAPI dependency: per-IP limit for /ask."""
    _enforce(ask_limiter, request)


def rate_limit_evals(request: Request) -> None:
    """FastAPI dependency: per-IP limit for /evals/retrieval."""
    _enforce(evals_limiter, request)


def ensure_table(conn: psycopg.Connection) -> None:
    """Create the spend ledger if missing. Idempotent; callers own the commit."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wallet_guard (
            day       DATE           PRIMARY KEY,
            spent_usd NUMERIC(10, 6) NOT NULL DEFAULT 0
        )
        """
    )


def spent_today(conn: psycopg.Connection) -> float:
    row = conn.execute("SELECT spent_usd FROM wallet_guard WHERE day = CURRENT_DATE").fetchone()
    return float(row[0]) if row else 0.0


def check_budget(conn: psycopg.Connection) -> None:
    """Raise 429 with a friendly message once today's spend reaches the cap."""
    spent = spent_today(conn)
    if spent >= config.DAILY_BUDGET_USD:
        logger.warning("daily budget reached: %.4f / %.2f USD", spent, config.DAILY_BUDGET_USD)
        raise HTTPException(429, BUDGET_MESSAGE)


def add_spend(conn: psycopg.Connection, usd: float) -> None:
    """Add to today's ledger row. Callers own the commit (or rollback in tests)."""
    conn.execute(
        """
        INSERT INTO wallet_guard (day, spent_usd) VALUES (CURRENT_DATE, %s)
        ON CONFLICT (day) DO UPDATE SET spent_usd = wallet_guard.spent_usd + EXCLUDED.spent_usd
        """,
        (usd,),
    )
