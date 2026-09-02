"""Wallet guard for the public deploy: rate limit + global daily budget cap.

Anyone can run up the LLM bill from a for-loop; this module is what prevents
that (ADR-0018). The app is public and has no accounts (a deliberate deploy
choice, same ADR), so the guards work without knowing who anyone is:

- Per-IP sliding-window rate limits on every paid endpoint. In-memory on
  purpose: state resets on restart, which under-counts briefly, and the budget
  cap below is the durable backstop.
- A global daily budget cap on paid API spend, persisted in the wallet_guard
  table (payments_rag.adapters.db, wallet_* functions) so it survives restarts
  and redeploys. Once the day's spend reaches DAILY_BUDGET_USD every paid
  endpoint returns 429 until UTC midnight.
- Question length is bounded on the request model (api.main.AskRequest).

This module is HTTP policy only (per ADR-0015/0017): it maps ledger state and
per-IP counters (api.rate_limit) to 429 responses. Spend accounting: /ask
records the measured LLM cost; eval and health runs pre-charge a flat,
deliberately-high estimate (charge_flat), so a run that fails halfway can
never spend unledgered money. Knobs live in payments_rag.config.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import psycopg
from fastapi import HTTPException, Request

from api.rate_limit import SlidingWindowLimiter
from payments_rag import config
from payments_rag.adapters import db

logger = logging.getLogger(__name__)

BUDGET_MESSAGE = (
    "The demo hit its daily API budget, so paid calls are paused to protect "
    "the owner's wallet. It resets at midnight UTC - come back tomorrow."
)
RATE_MESSAGE = "Rate limit reached for this endpoint. Try again in a bit."


def client_ip(request: Request) -> str:
    """The address the rate limiter keys on.

    fly-client-ip is set by Fly's proxy and cannot be forged by the client.
    Deliberately NOT x-forwarded-for: its first entry is client-supplied, so
    trusting it would let anyone mint a fresh rate-limit bucket per request.
    Off Fly (local dev, or another host per architecture.md) the TCP peer is
    the honest fallback.
    """
    return request.headers.get("fly-client-ip") or (
        request.client.host if request.client else "unknown"
    )


class RateLimiter:
    """Per-IP 429 mapping over SlidingWindowLimiter, usable as a FastAPI dependency."""

    def __init__(
        self, limit: int, window_s: int = 3600, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limiter = SlidingWindowLimiter(limit, window_s, clock)

    def retry_after(self, ip: str) -> int | None:
        return self._limiter.retry_after(ip)

    def reset(self) -> None:
        self._limiter.reset()

    def __call__(self, request: Request) -> None:
        wait = self.retry_after(client_ip(request))
        if wait is not None:
            logger.info("rate limit hit: %s %s", request.url.path, client_ip(request))
            raise HTTPException(429, RATE_MESSAGE, headers={"Retry-After": str(wait)})


ask_limiter = RateLimiter(config.RATE_LIMIT_ASK_PER_HOUR)
evals_limiter = RateLimiter(config.RATE_LIMIT_EVALS_PER_HOUR)
# The health tab makes paid pings too; without a limiter a curl loop could
# drain the whole daily budget through /health alone. Not env-tunable: 30/hour
# comfortably covers a human clicking through the tab.
health_limiter = RateLimiter(30)


def check_budget(conn: psycopg.Connection) -> None:
    """Raise 429 with a friendly message once today's spend reaches the cap."""
    spent = db.wallet_spent_today(conn)
    if spent >= config.DAILY_BUDGET_USD:
        logger.warning("daily budget reached: %.4f / %.2f USD", spent, config.DAILY_BUDGET_USD)
        raise HTTPException(429, BUDGET_MESSAGE)


def charge_flat(est_usd: float) -> None:
    """Gate on the budget and record a flat estimate, before the paid work runs.

    One connection for both steps. Charging up front means a run that fails
    halfway can never spend unledgered money; the estimates are deliberately
    high, so pre-charging errs on the safe side. If the DB itself is down we
    fail open (log and allow): the paid work will surface the outage anyway,
    and /health must keep rendering its diagnostics when Postgres is the thing
    that broke.
    """
    try:
        with db.connect() as conn:
            check_budget(conn)
            db.wallet_add_spend(conn, est_usd)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("budget check skipped (DB unreachable): %s", exc)
