"""FastAPI backend: exposes the Python core for the Angular frontend (ADR-0017).

    uv run uvicorn api.main:app --reload    # or: python -m uvicorn api.main:app

The core (orchestrator, retrieval, evals, query_log, health) is unchanged; this
is a thin HTTP layer over it. Interactive docs at /docs.

For the public deploy (ADR-0018) this layer also carries the wallet guard
(api/guard.py) and serves the built Angular SPA when frontend/dist exists, so
one container hosts both the API and the UI on the same origin.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import guard
from evals import retrieval_eval
from payments_rag import config, health, query_log
from payments_rag.adapters import db
from payments_rag.orchestrator import answer

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent.parent / "data"
_CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "raw"
_SPA_DIST = Path(
    os.environ.get(
        "SPA_DIST",
        Path(__file__).resolve().parent.parent / "frontend" / "dist" / "frontend" / "browser",
    )
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create the wallet_guard spend ledger if missing. Tolerate a DB that isn't
    # up yet: init.sql also creates the table, and /ask fails loudly anyway.
    try:
        with db.connect() as conn:
            guard.ensure_table(conn)
    except Exception as exc:
        logger.warning("wallet_guard table check skipped (DB unreachable): %s", exc)
    yield


app = FastAPI(title="Payments RAG API", version="0.1.0", lifespan=lifespan)
# In production the SPA is served from this same origin, so CORS stays closed
# unless CORS_ORIGINS says otherwise; the default covers the Angular dev server.
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:4200,http://127.0.0.1:4200"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware, allow_origins=_cors_origins, allow_methods=["*"], allow_headers=["*"]
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=config.MAX_QUESTION_CHARS)
    k: int = Field(5, ge=1, le=10)


@app.post("/ask")
def ask(req: AskRequest, _: None = Depends(guard.rate_limit_ask)) -> dict:
    with db.connect() as conn:
        guard.check_budget(conn)
        result = answer(conn, req.question, k=req.k)
        guard.add_spend(conn, result.cost_usd)
    query_log.log_query(
        req.question,
        mode="vector",
        k=req.k,
        wall_s=result.retrieval_s + result.generation_s,
        retrieval_s=result.retrieval_s,
        generation_s=result.generation_s,
        n_citations=len(result.citations),
        cost_usd=result.cost_usd,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    return {
        "answer": result.answer,
        "citations": [
            {"chunk_id": c.chunk_id, "source": c.source, "page": c.page, "text": c.text}
            for c in result.citations
        ],
        "timing": {"retrieval_s": result.retrieval_s, "generation_s": result.generation_s},
        "cost_usd": result.cost_usd,
        "tokens": {"input": result.input_tokens, "output": result.output_tokens},
    }


@app.get("/healthz")
def healthz() -> dict:
    """Liveness for the platform's health check: free, no DB, no paid pings."""
    return {"ok": True}


@app.get("/health")
def health_all() -> dict:
    _budget_gate()
    checks = health.check_all()
    _charge(guard.HEALTH_RUN_EST_USD)
    return {"checks": checks}


@app.post("/health/{name}")
def health_one(name: str) -> dict:
    if name not in health.NAMES:
        raise HTTPException(404, f"unknown dependency: {name} (try {health.NAMES})")
    if name in ("responder", "judge", "embeddings"):  # the paid pings
        _budget_gate()
        _charge(guard.HEALTH_RUN_EST_USD / 3)
    return health.check(name)


@app.post("/evals/retrieval")
def evals_retrieval(
    mode: str = "vector", k: int = 5, _: None = Depends(guard.rate_limit_evals)
) -> dict:
    _budget_gate()
    result = retrieval_eval.evaluate(k=k, hybrid=(mode == "hybrid"))
    _charge(guard.EVAL_RUN_EST_USD)
    return result


@app.get("/evals/answer")
def evals_answer() -> dict:
    path = _DATA / "last_answer_eval.json"
    if not path.exists():
        return {"empty": True}
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/usage")
def usage(limit: int = 50) -> dict:
    rows = query_log.read_queries(limit=limit)
    walls = [r["wall_s"] for r in rows if "wall_s" in r]
    costs = [r.get("cost_usd", 0.0) for r in rows]
    return {
        "count": len(rows),
        "avg_latency_s": round(sum(walls) / len(walls), 2) if walls else 0.0,
        "total_cost_usd": round(sum(costs), 4),
        "recent": rows[:25],
    }


@app.get("/source/{filename}")
def source(filename: str):
    """Serve a corpus PDF so the UI can deep-link to a page (#page=N)."""
    path = _CORPUS / Path(filename).name  # .name strips any path-traversal
    if not path.exists() or path.suffix.lower() != ".pdf":
        raise HTTPException(404, f"not found: {filename}")
    return FileResponse(path, media_type="application/pdf")


def _budget_gate() -> None:
    """Enforce the daily cap for endpoints that make paid calls outside /ask."""
    with db.connect() as conn:
        guard.check_budget(conn)


def _charge(usd: float) -> None:
    with db.connect() as conn:
        guard.add_spend(conn, usd)


class _SpaStaticFiles(StaticFiles):
    """Static files with an index.html fallback so SPA routes survive a refresh."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # Starlette raises its own HTTPException here, not FastAPI's subclass.
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


# Mounted last so every API route above wins; only unmatched paths hit the SPA.
if _SPA_DIST.is_dir():
    app.mount("/", _SpaStaticFiles(directory=_SPA_DIST, html=True), name="spa")
