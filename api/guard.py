"""Wallet guard for the public deploy: rate limit + global daily budget cap.

Anyone can run up the LLM bill from a for-loop; this module is what prevents
that (ADR-0018). The app is public and has no accounts (a deliberate deploy
choice, same ADR), so the guards work without knowing who anyone is:

- Per-IP sliding-window rate limits on every paid endpoint. In-memory on
  purpose: state resets on restart, which under-counts briefly, and the budget
  cap below is the durable backstop.
- A global daily budget cap on paid API spend, persisted in the wallet_guard
  table so it survives restarts and redeploys. Once the day's spend reaches
  DAILY_BUDGET_USD every paid endpoint returns 429 until UTC midnight.
- Question length is bounded on the request model (api.main.AskRequest).

Spend accounting: /ask records the measured LLM cost from the orchestrator.
The eval and health endpoints charge a flat, deliberately-high estimate UP
FRONT (charge_flat), so a run that fails halfway can never spend unledgered
money. Knobs live in payments_rag.config.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

import psycopg
from fastapi import HTTPException, Request

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
    """Sliding-window per-IP counter, usable directly as a FastAPI dependency:

        @app.post("/ask")
        def ask(_: None = Depends(guard.ask_limiter)) -> ...

    `clock` is injectable for tests.
    """

    def __init__(
        self, limit: int, window_s: int = 3600, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = clock()
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
            self._maybe_sweep(now)
            return None

    def _maybe_sweep(self, now: float) -> None:
        """Drop stale IPs, at most once per window, to bound memory over months."""
        if now - self._last_sweep < self.window_s:
            return
        self._last_sweep = now
        stale = [k for k, v in self._hits.items() if not v or now - v[-1] > self.window_s]
        for key in stale:
            del self._hits[key]

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


def ensure_table(conn: psycopg.Connection) -> None:
    """Create the spend ledger if missing. Idempotent; callers own the commit.

    The same DDL lives in infra/init.sql for fresh databases; this is the
    self-heal path for databases created before the table existed.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wallet_guard (
            day       DATE           PRIMARY KEY,
            spent_usd NUMERIC(10, 6) NOT NULL DEFAULT 0
        )
        """
    )


def _with_table(conn: psycopg.Connection, fn: Callable[[], object]) -> object:
    """Run fn; on UndefinedTable, roll back, create the ledger, retry once.

    The rollback discards the caller's uncommitted work, so budget calls must
    come FIRST in a request's transaction (they do: gate before paid work).
    """
    try:
        return fn()
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        ensure_table(conn)
        return fn()


def spent_today(conn: psycopg.Connection) -> float:
    def query():
        return conn.execute(
            "SELECT spent_usd FROM wallet_guard WHERE day = CURRENT_DATE"
        ).fetchone()

    row = _with_table(conn, query)
    return float(row[0]) if row else 0.0


def check_budget(conn: psycopg.Connection) -> None:
    """Raise 429 with a friendly message once today's spend reaches the cap."""
    spent = spent_today(conn)
    if spent >= config.DAILY_BUDGET_USD:
        logger.warning("daily budget reached: %.4f / %.2f USD", spent, config.DAILY_BUDGET_USD)
        raise HTTPException(429, BUDGET_MESSAGE)


def add_spend(conn: psycopg.Connection, usd: float) -> None:
    """Add to today's ledger row. Callers own the commit (or rollback in tests)."""

    def upsert():
        conn.execute(
            """
            INSERT INTO wallet_guard (day, spent_usd) VALUES (CURRENT_DATE, %s)
            ON CONFLICT (day) DO UPDATE
                SET spent_usd = wallet_guard.spent_usd + EXCLUDED.spent_usd
            """,
            (usd,),
        )

    _with_table(conn, upsert)


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
            add_spend(conn, est_usd)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("budget check skipped (DB unreachable): %s", exc)
