"""Re-measure the payments-rag pipeline on a healthy system.

Three measurements, per the job request:
  1. end-to-end query time, split into retrieval vs generation
  2. vector search (KNN) isolated from the rest of the retrieval stage
  3. EXPLAIN ANALYZE for that KNN query

Measure, do not fix. Anything that looks wrong is recorded, not corrected.
Writes raw JSON so the numbers can be re-opened; prints a summary.
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

sys.path.insert(0, ".")

import yaml  # noqa: E402

from payments_rag import config  # noqa: E402
from payments_rag.adapters import db  # noqa: E402
from payments_rag.adapters.embedding import embed_one  # noqa: E402
from payments_rag.answering.orchestrator import answer  # noqa: E402

OUT = Path("docs/measurements")
OUT.mkdir(parents=True, exist_ok=True)
STAMP = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def stats(xs: list[float]) -> dict:
    """Summarise a list of durations (seconds) in milliseconds."""
    if not xs:
        return {}
    s = sorted(xs)
    return {
        "n": len(s),
        "median_ms": round(statistics.median(s) * 1000, 3),
        "mean_ms": round(statistics.fmean(s) * 1000, 3),
        "min_ms": round(min(s) * 1000, 3),
        "max_ms": round(max(s) * 1000, 3),
        "p90_ms": round(s[int(len(s) * 0.9) - 1] * 1000, 3) if len(s) >= 10 else None,
    }


report: dict = {"meta": {}, "context": {}, "measurements": {}}

# --------------------------------------------------------------------------
# Context: machine, instance, corpus. A latency figure without its context is
# how the original number went wrong.
# --------------------------------------------------------------------------
from urllib.parse import urlparse  # noqa: E402

u = urlparse(config.DATABASE_URL)
report["meta"] = {
    "taken_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    "machine": f"{platform.system()} {platform.release()} ({platform.machine()})",
    "python": platform.python_version(),
    "instance": f"local Postgres {u.hostname}:{u.port}/{u.path.lstrip('/')}",
    "llm_model": config.LLM_MODEL,
    "embed_model": config.EMBED_MODEL,
    "db_host_literal": u.hostname,  # 127.0.0.1 means the localhost/IPv6 bug is NOT active
}

print("=== connect (health gate) ===")
connect_times = []
for _ in range(5):
    t = perf_counter()
    c = db.connect()
    connect_times.append(perf_counter() - t)
    c.close()
report["context"]["connect"] = stats(connect_times)
print("  connect:", report["context"]["connect"])

conn = db.connect()
n_chunks = db.count(conn)
srcs = db.source_counts(conn)
pg_version = conn.execute("SHOW server_version").fetchone()[0]
try:
    vec_ext = conn.execute(
        "SELECT extversion FROM pg_extension WHERE extname='vector'"
    ).fetchone()[0]
except Exception:
    vec_ext = "unknown"
indexes = conn.execute(
    "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='chunks'"
).fetchall()
report["context"].update(
    {
        "chunks": n_chunks,
        "sources": {s: k for s, k in srcs},
        "postgres_version": pg_version,
        "pgvector_version": vec_ext,
        "indexes": {name: definition for name, definition in indexes},
    }
)
print(f"  chunks: {n_chunks} | pg {pg_version} | pgvector {vec_ext}")
for name, _ in indexes:
    print("  index:", name)

# --------------------------------------------------------------------------
# Golden-set questions: real user phrasings, not synthetic.
# --------------------------------------------------------------------------
golden = yaml.safe_load(Path("evals/retrieval_golden_set.yaml").read_text(encoding="utf-8"))
questions = [g["question"] for g in golden]
print(f"\n=== {len(questions)} golden questions ===")

# --------------------------------------------------------------------------
# MEASUREMENT 2 (run first, it is free): KNN isolated.
# Query vector is taken from a stored row, so no embedding API call pollutes it.
# --------------------------------------------------------------------------
print("\n=== KNN isolated (stored vector, no API call) ===")
stored_vec = conn.execute("SELECT embedding FROM chunks ORDER BY id LIMIT 1").fetchone()[0]
for _ in range(5):  # warm the connection and plan cache
    db.nearest(conn, stored_vec, k=5)
knn = []
for _ in range(50):
    t = perf_counter()
    db.nearest(conn, stored_vec, k=5)
    knn.append(perf_counter() - t)
report["measurements"]["knn_isolated"] = {
    "method": "db.nearest(conn, stored_vector, k=5), timed in Python incl. driver overhead, 50 runs after 5 warm-ups",
    **stats(knn),
}
print("  knn:", report["measurements"]["knn_isolated"])

# --------------------------------------------------------------------------
# MEASUREMENT 2b: embedding call isolated (paid, but pennies).
# retrieval_s = embed_one() + db.nearest(), so this completes the split.
# --------------------------------------------------------------------------
print("\n=== embedding call isolated (one per golden question) ===")
emb = []
for q in questions:
    t = perf_counter()
    embed_one(q)
    emb.append(perf_counter() - t)
report["measurements"]["embed_isolated"] = {
    "method": "embed_one(question) over the 10 golden questions, one call each",
    **stats(emb),
}
print("  embed:", report["measurements"]["embed_isolated"])

# --------------------------------------------------------------------------
# MEASUREMENT 1: end-to-end via the real orchestrator, 3 rounds x 10 questions.
# --------------------------------------------------------------------------
print("\n=== end-to-end (orchestrator.answer) ===")
runs = []
for round_i in range(3):
    for q in questions:
        t = perf_counter()
        r = answer(conn, q, k=5)
        wall = perf_counter() - t
        runs.append(
            {
                "round": round_i,
                "question": q,
                "wall_s": wall,
                "retrieval_s": r.retrieval_s,
                "generation_s": r.generation_s,
                "cost_usd": r.cost_usd,
                "citations": len(r.citations),
            }
        )
        print(
            f"  r{round_i} {wall:6.2f}s  (retr {r.retrieval_s:5.2f} / gen {r.generation_s:5.2f})  {q[:48]}"
        )

warm = [x for x in runs if not (x["round"] == 0 and x["question"] == questions[0])]
report["measurements"]["end_to_end"] = {
    "method": "orchestrator.answer(conn, q, k=5) over 10 golden questions x 3 rounds; first call excluded from stats as cold",
    "cold_first_call": {
        "wall_ms": round(runs[0]["wall_s"] * 1000, 1),
        "retrieval_ms": round(runs[0]["retrieval_s"] * 1000, 1),
        "generation_ms": round(runs[0]["generation_s"] * 1000, 1),
    },
    "wall": stats([x["wall_s"] for x in warm]),
    "retrieval": stats([x["retrieval_s"] for x in warm]),
    "generation": stats([x["generation_s"] for x in warm]),
    "total_cost_usd": round(sum(x["cost_usd"] for x in runs), 4),
    "raw": runs,
}
e2e = report["measurements"]["end_to_end"]
print(f"\n  wall      : {e2e['wall']}")
print(f"  retrieval : {e2e['retrieval']}")
print(f"  generation: {e2e['generation']}")
print(f"  spend     : ${e2e['total_cost_usd']}")

# --------------------------------------------------------------------------
# MEASUREMENT 3: EXPLAIN ANALYZE on the KNN query (local instance).
# --------------------------------------------------------------------------
print("\n=== EXPLAIN ANALYZE (local) ===")
SQL = """
        SELECT id, source, text, page, embedding <=> %s::vector AS distance
        FROM chunks
        ORDER BY distance ASC
        LIMIT %s
"""
plan_rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + SQL, (db._vec(stored_vec), 5)).fetchall()
plan = [r[0][:300] for r in plan_rows]  # truncate: the sort key echoes the whole vector literal
report["measurements"]["explain_local"] = {
    "method": "EXPLAIN (ANALYZE, BUFFERS) on the exact db.nearest query, k=5, lines truncated to 300 chars",
    "uses_hnsw_index": any("chunks_embedding_idx" in ln or "Index Scan" in ln for ln in plan),
    "plan": plan,
}
for ln in plan:
    print("   ", ln[:160])

# Diagnostic only, session-local, changes nothing on disk: can the planner use
# the HNSW index at all if told to avoid a sequential scan?
conn.execute("SET LOCAL enable_seqscan = off")
plan_rows2 = conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + SQL, (db._vec(stored_vec), 5)).fetchall()
plan2 = [r[0][:300] for r in plan_rows2]
conn.rollback()
report["measurements"]["explain_local_seqscan_off"] = {
    "method": "same query with SET LOCAL enable_seqscan = off (session-local diagnostic, rolled back)",
    "uses_hnsw_index": any("chunks_embedding_idx" in ln or "Index Scan" in ln for ln in plan2),
    "plan": plan2,
}
print("\n=== EXPLAIN ANALYZE (local, enable_seqscan=off diagnostic) ===")
for ln in plan2:
    print("   ", ln[:160])

conn.close()

out = OUT / f"pipeline-timings-{STAMP}.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
