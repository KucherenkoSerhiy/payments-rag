"""Append-only query log: the telemetry the Usage view reads.

One JSON object per line (JSONL) in data/queries.jsonl: when, what was asked, the
retrieval mode, and the per-stage timings. Cost is intentionally absent: we
don't capture token counts yet (a later addition); latency is what we have.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_LOG = Path(__file__).resolve().parent.parent / "data" / "queries.jsonl"


def log_query(
    question: str,
    *,
    mode: str,
    k: int,
    wall_s: float,
    retrieval_s: float,
    generation_s: float,
    n_citations: int,
    cost_usd: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Append one query event. Best-effort; never let logging break a request."""
    row = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "mode": mode,
        "k": k,
        "wall_s": round(wall_s, 2),
        "retrieval_s": round(retrieval_s, 2),
        "generation_s": round(generation_s, 2),
        "n_citations": n_citations,
        "cost_usd": round(cost_usd, 6),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def read_queries(limit: int = 50) -> list[dict]:
    """Most recent first; [] if nothing has been logged yet."""
    if not _LOG.exists():
        return []
    rows = [json.loads(line) for line in _LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    return list(reversed(rows))[:limit]
