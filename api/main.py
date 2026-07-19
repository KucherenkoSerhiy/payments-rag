"""FastAPI backend: exposes the Python core for the Angular frontend (ADR-0017).

    uv run uvicorn api.main:app --reload    # or: python -m uvicorn api.main:app

The core (orchestrator, retrieval, evals, query_log, health) is unchanged; this
is a thin HTTP layer over it. Interactive docs at /docs.

For the public deploy (ADR-0018) requests pass the wallet guard (api/guard.py)
and the built Angular SPA is served from this same origin (api/spa.py).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api import guard, spa
from evals import retrieval_eval
from payments_rag import config, health, query_log
from payments_rag.adapters import db
from payments_rag.orchestrator import answer

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data"
_CORPUS = _ROOT / "corpus" / "raw"

app = FastAPI(title="Payments RAG API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=config.MAX_QUESTION_CHARS)
    k: int = Field(5, ge=1, le=10)


@app.post("/ask")
def ask(req: AskRequest, _: None = Depends(guard.ask_limiter)) -> dict:
    with db.connect() as conn:
        guard.check_budget(conn)
        result = answer(conn, req.question, k=req.k)
        try:
            db.wallet_add_spend(conn, result.cost_usd)
        except Exception as exc:
            # The answer is already paid for; a ledger hiccup must not 500 it.
            logger.warning("spend not recorded (%.6f USD): %s", result.cost_usd, exc)
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
def health_all(_: None = Depends(guard.health_limiter)) -> dict:
    guard.charge_flat(config.HEALTH_RUN_EST_USD)
    return {"checks": health.check_all()}


@app.post("/health/{name}")
def health_one(name: str, _: None = Depends(guard.health_limiter)) -> dict:
    if name not in health.NAMES:
        raise HTTPException(404, f"unknown dependency: {name} (try {health.NAMES})")
    if name in health.PAID_NAMES:
        guard.charge_flat(config.HEALTH_RUN_EST_USD / len(health.PAID_NAMES))
    return health.check(name)


@app.post("/evals/retrieval")
def evals_retrieval(
    mode: str = "vector", k: int = 5, _: None = Depends(guard.evals_limiter)
) -> dict:
    guard.charge_flat(config.EVAL_RUN_EST_USD)
    return retrieval_eval.evaluate(k=k, hybrid=(mode == "hybrid"))


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


spa.mount_spa(app)
