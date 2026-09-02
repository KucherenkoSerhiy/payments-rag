"""Tests for the deployed ask use case: answer + spend ledger + telemetry.

No DB and no API: the orchestrator, ledger, and telemetry seams are
monkeypatched; these tests check only the service's own contract.
"""

from __future__ import annotations

from payments_rag.answering import service
from payments_rag.domain import AnswerResult

RESULT = AnswerResult(answer="stub", citations=[], retrieval_s=0.1, generation_s=0.2, cost_usd=0.003)


def test_ask_answers_records_spend_and_logs(monkeypatch) -> None:
    spends: list[float] = []
    logged: list[dict] = []
    monkeypatch.setattr(service, "answer", lambda conn, q, k=5: RESULT)
    monkeypatch.setattr(service.db, "wallet_add_spend", lambda conn, usd: spends.append(usd))
    monkeypatch.setattr(service.query_log, "log_query", lambda q, **kw: logged.append({"q": q, **kw}))

    result = service.ask(conn=None, question="how fast?", k=3)

    assert result is RESULT
    assert spends == [0.003]
    assert logged[0]["q"] == "how fast?"
    assert logged[0]["k"] == 3
    assert logged[0]["cost_usd"] == 0.003
    assert logged[0]["wall_s"] == RESULT.retrieval_s + RESULT.generation_s


def test_ledger_failure_does_not_fail_the_answer(monkeypatch) -> None:
    logged: list[str] = []
    monkeypatch.setattr(service, "answer", lambda conn, q, k=5: RESULT)
    monkeypatch.setattr(
        service.db, "wallet_add_spend", lambda conn, usd: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    monkeypatch.setattr(service.query_log, "log_query", lambda q, **kw: logged.append(q))

    result = service.ask(conn=None, question="q")

    assert result is RESULT  # the answer is already paid for; it must still be returned
    assert logged == ["q"]  # and telemetry still happens
