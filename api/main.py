"""FastAPI backend — exposes the Python core for the Angular frontend (ADR-0017).

    uv run uvicorn api.main:app --reload    # or: python -m uvicorn api.main:app

The core (orchestrator, retrieval, evals, query_log, health) is unchanged; this
is a thin HTTP layer over it. Interactive docs at /docs.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from evals import retrieval_eval
from payments_rag import health, query_log
from payments_rag.adapters import db
from payments_rag.orchestrator import answer

_DATA = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="Payments RAG API", version="0.1.0")
# Dev-open CORS so the Angular dev server can call the API; tighten for deploy.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class AskRequest(BaseModel):
    question: str
    k: int = 5


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    with db.connect() as conn:
        result = answer(conn, req.question, k=req.k)
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


@app.get("/health")
def health_all() -> dict:
    return {"checks": health.check_all()}


@app.post("/health/{name}")
def health_one(name: str) -> dict:
    if name not in health.NAMES:
        raise HTTPException(404, f"unknown dependency: {name} (try {health.NAMES})")
    return health.check(name)


@app.post("/evals/retrieval")
def evals_retrieval(mode: str = "vector", k: int = 5) -> dict:
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
