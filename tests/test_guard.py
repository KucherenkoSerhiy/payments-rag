"""Tests for the wallet guard: rate limiter, input bounds, budget cap.

The limiter and request-validation tests are pure (no DB, no API keys). The
ledger tests use the shared `conn` fixture (tests/conftest.py): they need the
docker-compose Postgres, skip without it, and roll back all test spend.
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


@pytest.fixture(autouse=True)
def _fresh_limiters():
    """The module-level limiters are process-global; don't leak hits across tests."""
    for limiter in (guard.ask_limiter, guard.evals_limiter, guard.health_limiter):
        limiter.reset()
    yield
    app.dependency_overrides.clear()


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


def test_client_ip_ignores_x_forwarded_for() -> None:
    """XFF is client-supplied; trusting it would let anyone dodge the limiter."""

    class Req:
        headers = {"x-forwarded-for": "6.6.6.6"}

        class client:
            host = "10.0.0.1"

    assert guard.client_ip(Req()) == "10.0.0.1"


def test_ask_rejects_overlong_question() -> None:
    client = TestClient(app)
    too_long = "x" * (config.MAX_QUESTION_CHARS + 1)
    assert client.post("/ask", json={"question": too_long}).status_code == 422


def test_ask_rejects_out_of_range_k() -> None:
    client = TestClient(app)
    assert client.post("/ask", json={"question": "q", "k": 99}).status_code == 422


def test_ask_hits_rate_limit_with_friendly_429(monkeypatch) -> None:
    # Depends(guard.ask_limiter) binds the instance at import; override it here.
    app.dependency_overrides[guard.ask_limiter] = guard.RateLimiter(limit=1)
    # no paid calls, no DB: stub the answer path end to end
    result = AnswerResult(answer="stub", citations=[])

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("api.main.db.connect", lambda: FakeConn())
    monkeypatch.setattr("api.main.guard.check_budget", lambda conn: None)
    monkeypatch.setattr("api.main.db.wallet_add_spend", lambda conn, usd: None)
    monkeypatch.setattr("api.main.answer", lambda conn, q, k=5: result)
    monkeypatch.setattr("api.main.query_log.log_query", lambda *a, **kw: None)

    client = TestClient(app)
    assert client.post("/ask", json={"question": "q"}).status_code == 200
    blocked = client.post("/ask", json={"question": "q"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_budget_ledger_accumulates_and_trips(conn, monkeypatch) -> None:
    monkeypatch.setattr(config, "DAILY_BUDGET_USD", 0.01)
    db.wallet_ensure_table(conn)
    base = db.wallet_spent_today(conn)
    db.wallet_add_spend(conn, 0.004)
    db.wallet_add_spend(conn, 0.004)
    assert abs(db.wallet_spent_today(conn) - (base + 0.008)) < 1e-9
    db.wallet_add_spend(conn, 0.004)
    with pytest.raises(HTTPException) as exc:
        guard.check_budget(conn)
    assert exc.value.status_code == 429


def test_ledger_self_heals_missing_table(conn) -> None:
    """Databases created before wallet_guard existed must not 500 /ask forever.

    The in-transaction DROP makes the first query raise UndefinedTable; the
    adapter's recovery (rollback + create + retry) must absorb it. The
    rollback also undoes the DROP here, so only recovery is asserted, not an
    empty ledger.
    """
    conn.execute("DROP TABLE wallet_guard")
    assert db.wallet_spent_today(conn) >= 0.0  # recovered, no exception escaped
    db.wallet_add_spend(conn, 0.001)  # ledger writable after recovery
