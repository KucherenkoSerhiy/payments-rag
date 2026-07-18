"""Tests for the wallet guard: rate limiter, input bounds, budget cap.

The limiter and request-validation tests are pure (no DB, no API keys). The
ledger tests need the live Postgres from docker-compose, same as
test_db_integration, and roll back so they never pollute today's real spend.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import guard
from api.main import app
from payments_rag import config
from payments_rag.adapters import db
from payments_rag.orchestrator import AnswerResult


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_allows_up_to_limit_then_blocks() -> None:
    limiter = guard.RateLimiter(limit=3, window_s=3600, clock=FakeClock())
    assert [limiter.retry_after("1.2.3.4") for _ in range(3)] == [None, None, None]
    wait = limiter.retry_after("1.2.3.4")
    assert wait is not None and wait > 0
    # a different ip is unaffected
    assert limiter.retry_after("5.6.7.8") is None


def test_rate_limiter_window_slides() -> None:
    clock = FakeClock()
    limiter = guard.RateLimiter(limit=2, window_s=3600, clock=clock)
    assert limiter.retry_after("ip") is None
    assert limiter.retry_after("ip") is None
    assert limiter.retry_after("ip") is not None
    clock.now += 3601  # both hits age out
    assert limiter.retry_after("ip") is None


def test_ask_rejects_overlong_question() -> None:
    client = TestClient(app)
    too_long = "x" * (config.MAX_QUESTION_CHARS + 1)
    assert client.post("/ask", json={"question": too_long}).status_code == 422


def test_ask_rejects_out_of_range_k() -> None:
    client = TestClient(app)
    assert client.post("/ask", json={"question": "q", "k": 99}).status_code == 422


def test_ask_hits_rate_limit_with_friendly_429(monkeypatch) -> None:
    monkeypatch.setattr("api.main.guard.ask_limiter", guard.RateLimiter(limit=1, window_s=3600))
    # no paid calls, no DB: stub the answer path end to end
    result = AnswerResult(
        answer="stub",
        citations=[],
        retrieval_s=0.0,
        generation_s=0.0,
        cost_usd=0.0,
        input_tokens=1,
        output_tokens=1,
    )

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("api.main.db.connect", lambda: FakeConn())
    monkeypatch.setattr("api.main.guard.check_budget", lambda conn: None)
    monkeypatch.setattr("api.main.guard.add_spend", lambda conn, usd: None)
    monkeypatch.setattr("api.main.answer", lambda conn, q, k=5: result)
    monkeypatch.setattr("api.main.query_log.log_query", lambda *a, **kw: None)

    client = TestClient(app)
    assert client.post("/ask", json={"question": "q"}).status_code == 200
    blocked = client.post("/ask", json={"question": "q"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


@pytest.fixture
def conn():
    try:
        c = db.connect()
    except Exception as exc:  # no DB reachable (e.g. a fresh clone)
        pytest.skip(f"no database available: {exc}")
    try:
        yield c
    finally:
        c.rollback()  # never persist test spend into today's real ledger
        c.close()


def test_budget_ledger_accumulates_and_trips(conn, monkeypatch) -> None:
    """Needs the docker-compose Postgres; the fixture rolls back all test spend."""
    monkeypatch.setattr(config, "DAILY_BUDGET_USD", 0.01)
    guard.ensure_table(conn)
    base = guard.spent_today(conn)
    guard.add_spend(conn, 0.004)
    guard.add_spend(conn, 0.004)
    assert abs(guard.spent_today(conn) - (base + 0.008)) < 1e-9
    guard.add_spend(conn, 0.004)
    with pytest.raises(HTTPException) as exc:
        guard.check_budget(conn)
    assert exc.value.status_code == 429
