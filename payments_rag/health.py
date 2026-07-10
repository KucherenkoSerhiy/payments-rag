"""Multi-dependency health checks — DB, responder, judge, embeddings, service.

Each check returns {name, kind, ok, latency_ms, detail, at}. The remote checks
make a minimal (1-token / short-string) call, so they cost ~nothing but confirm
the integration is actually reachable AND authorized — not merely configured.
"""

from __future__ import annotations

from datetime import datetime
from time import perf_counter

from payments_rag import config
from payments_rag.adapters import db

_START = perf_counter()  # process-uptime proxy (module import time)


def _timed(kind: str, name: str, fn) -> dict:
    at = datetime.now().isoformat(timespec="seconds")
    t0 = perf_counter()
    try:
        detail = fn()
        ok = True
    except Exception as exc:  # unreachable / unauthorized / timeout
        detail, ok = str(exc), False
    return {
        "name": name,
        "kind": kind,
        "ok": ok,
        "latency_ms": round((perf_counter() - t0) * 1000),
        "detail": detail,
        "at": at,
    }


def check_database() -> dict:
    def ping():
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return "SELECT 1 ok"

    return _timed("Postgres · pgvector", "database", ping)


def check_responder() -> dict:
    def ping():
        from anthropic import Anthropic

        client = Anthropic(api_key=config.require_anthropic_key(), timeout=config.API_TIMEOUT, max_retries=1)
        client.messages.create(model=config.LLM_MODEL, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
        return config.LLM_MODEL

    return _timed(f"Claude · {config.LLM_MODEL}", "responder", ping)


def check_judge() -> dict:
    def ping():
        from openai import OpenAI

        client = OpenAI(api_key=config.require_openai_key(), timeout=config.API_TIMEOUT, max_retries=1)
        client.chat.completions.create(model=config.JUDGE_MODEL, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
        return config.JUDGE_MODEL

    return _timed(f"GPT · {config.JUDGE_MODEL}", "judge", ping)


def check_embeddings() -> dict:
    def ping():
        from payments_rag.adapters.embedding import embed_one

        return f"{len(embed_one('ping'))}-dim vector"

    return _timed(f"OpenAI · {config.EMBED_MODEL}", "embeddings", ping)


def check_service() -> dict:
    return {
        "name": "service",
        "kind": "this app",
        "ok": True,
        "latency_ms": 0,
        "detail": f"uptime {round(perf_counter() - _START)}s",
        "at": datetime.now().isoformat(timespec="seconds"),
    }


_CHECKS = {
    "database": check_database,
    "responder": check_responder,
    "judge": check_judge,
    "embeddings": check_embeddings,
    "service": check_service,
}
NAMES = list(_CHECKS)


def check(name: str) -> dict:
    """Run one dependency's check. Raises KeyError for an unknown name."""
    return _CHECKS[name]()


def check_all() -> list[dict]:
    return [fn() for fn in _CHECKS.values()]
