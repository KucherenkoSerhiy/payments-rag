# payments-rag pipeline timings, re-measured on a healthy system

**Taken:** 2026-07-28, 21:32 CEST
**Why:** an earlier figure, "vector search is 3.7 ms of a 2,100 ms pipeline", was quoted in write-ups about this project. Its denominator came from a trace recorded while the localhost/IPv6 connect bug was active, so it was measured on a broken system and needed re-taking.

> **Artifact status: committed.** Raw JSON alongside this file: `pipeline-timings-2026-07-28.json` (local suite, full per-query rows) and `prod-ask-2026-07-28.json` (production API calls). First written to `data/`, which is gitignored, then moved here so the numbers are citable rather than local-only.

---

## Context

| | Local | Production |
|---|---|---|
| Instance | Postgres 17.10 + pgvector 0.8.2, Docker, `127.0.0.1:5433` | Neon, Postgres 18.4 + pgvector 0.8.1, behind Fly.io |
| Machine | Windows 11, AMD64, Python 3.14.0 | Fly.io container; API calls made from Barcelona |
| Corpus | 484 chunks (sct_inst 236, sct 248) | 484 chunks (verified on Neon) |
| Models | claude-haiku-4-5, text-embedding-3-small | same |
| Indexes on `chunks` | `chunks_embedding_idx` HNSW (vector_cosine_ops), `chunks_text_fts_idx` GIN, `chunks_pkey` btree | same three |

Production numbers were taken by running the same code inside the Fly container via `fly ssh console`, so the Neon connection string never left the deployment. Read-only throughout: `EXPLAIN ANALYZE` on a `SELECT`, plus timed KNN queries.

Note on production shape: the Fly machine scales to zero. A cold request took **15.4 s** to return health while the machine woke. That is a deployment property, not a pipeline cost, and it is excluded from the timings below, which were all taken against a warm machine.

**Health gate.** `DATABASE_URL` resolves to `127.0.0.1`, not `localhost`, so the IPv6 bug is not active. Connect: **median 31.1 ms** (n=5, min 23.2, max 51.3). The broken-system trace showed ~10,137 ms for the same operation. The system measured here is healthy.

Production health at time of measurement: database 234 ms, responder 693 ms, judge 553 ms, embeddings 172 ms, service 0 ms. All reachable.

---

## Measurement 1: end-to-end, split into retrieval and generation

`orchestrator.answer(conn, q, k=5)` over the 10 golden-set questions, 3 rounds, 30 answers. First call excluded as cold (client construction). Medians over the remaining 29.

**Local**

| Stage | Median | Mean | Min | p90 | Max |
|---|---|---|---|---|---|
| Wall (end-to-end) | **2,823 ms** | 3,610 ms | 1,983 ms | 3,751 ms | 21,423 ms |
| Retrieval | **224 ms** | 245 ms | 180 ms | 341 ms | 400 ms |
| Generation | **2,598 ms** | 3,366 ms | 1,743 ms | 3,516 ms | 21,209 ms |

Cold first call: 4,285 ms wall (retrieval 217 ms, generation 4,064 ms).
Spend for this measurement: **$0.0824**.

The 21.4 s maximum is a single slow Claude call in round 0. It is a real tail and it moves the mean; the median is the honest central figure.

**Production** (public API, 5 queries, server-reported timings)

| Stage | Median |
|---|---|
| Retrieval | **161 ms** |
| Generation | **2,028 ms** |
| Server total | **2,189 ms** |
| Wall incl. my network round trip | 3,441 ms |

Production retrieval is slightly *faster* than local (161 vs 224 ms), so the Neon round trip is not a penalty in the deployed topology.

---

## Measurement 2: vector search isolated

`db.nearest(conn, stored_vector, k=5)`, query vector taken from a stored row so no embedding API call pollutes the timing. 50 runs after 5 warm-ups, timed in Python including driver overhead.

**KNN, local: median 4.884 ms** (mean 5.017, min 4.137, p90 5.691, max 6.828).

The embedding call, timed separately over the same 10 questions: median 277 ms (mean 669, min 191, max 3,160; the mean is dragged by one cold 3.2 s call).

So the retrieval stage decomposes as:

```
retrieval stage        224 ms   (100%)
  embedding API call  ~219 ms   (97.8%)   <- derived: retrieval minus KNN
  vector search (KNN)   4.9 ms   (2.2%)
```

**The "the slow part was the embedding API call" claim is confirmed.** It is 98% of the retrieval stage.

**KNN, production (Neon, measured from the app container): median 17.263 ms** (n=30, min 16.879, max 26.761).

That is 3.5x the local figure, and the gap is the network. Neon's own server-side execution is *faster* than local (2.601 ms vs 3.902 ms, see below); the extra ~14 ms is the round trip from the Fly container to Neon. So the production retrieval stage decomposes as:

```
retrieval stage        161 ms   (100%)
  embedding API call  ~144 ms   (89.3%)   <- derived: retrieval minus KNN
  vector search (KNN)   17.3 ms  (10.7%)
```

The embedding call still dominates in production, but the database is a tenth of the stage rather than a fiftieth. Caveat: the 161 ms retrieval median and the 17.3 ms KNN median come from separate samples taken minutes apart, so treat the split as approximate.

---

## Measurement 3: EXPLAIN ANALYZE on the KNN query

Exact `db.nearest` query, k=5, local instance.

**Default plan: sequential scan, no index.**

```
Limit  (cost=150.09..150.10 rows=5) (actual time=3.874..3.878 rows=5 loops=1)
  Buffers: shared hit=1588
  ->  Sort  (cost=150.09..151.30 rows=484) (actual time=3.871..3.873 rows=5)
        Sort Method: top-N heapsort  Memory: 33kB
        ->  Seq Scan on chunks  (cost=0.00..142.05 rows=484) (actual time=0.056..3.570 rows=484)
Planning Time: 0.175 ms
Execution Time: 3.902 ms
```

**Diagnostic, same query with `SET LOCAL enable_seqscan = off` (session-local, rolled back):**

```
Limit  (cost=2145.81..2158.58 rows=5) (actual time=66.449..66.510 rows=5 loops=1)
  Buffers: shared hit=75 read=183
  ->  Index Scan using chunks_embedding_idx on chunks  (actual time=66.446..66.505 rows=5)
Execution Time: 66.551 ms
```

The article's claim that the planner does not use the HNSW index is **confirmed on local**. The stronger finding is *why*: forcing the index makes the query **17x slower** (66.6 ms vs 3.9 ms), because at 484 rows the index costs 183 page reads while the sequential scan runs entirely from cache. The planner is not being naive, it is correct.

**Neon, same query, run from inside the production container:**

```
Limit  (cost=109.09..109.10 rows=5) (actual time=2.577..2.578 rows=5.00 loops=1)
  Buffers: shared hit=1547
  ->  Sort  (cost=109.09..110.30 rows=484) (actual time=2.575..2.576 rows=5.00)
        Sort Method: top-N heapsort  Memory: 33kB
        ->  Seq Scan on chunks  (cost=0.00..101.05 rows=484) (actual time=0.043..2.331 rows=484.00)
Planning Time: 0.086 ms
Execution Time: 2.601 ms
```

**The two instances agree.** Neon also picks a sequential scan with a top-N heapsort and ignores the HNSW index, on a different major version (18.4 vs 17.10) and a different pgvector build (0.8.1 vs 0.8.2). Two independent planners reaching the same decision is much stronger evidence than one, so the claim can now be stated for this corpus size rather than for one machine.

Neon executes it slightly faster server-side (2.601 ms vs 3.902 ms). The client-observed difference (17.3 ms vs 4.9 ms) is network, not database.

---

## Verdict on "3.7 ms of a 2,100 ms pipeline"

**The conclusion survives. The numbers behind it do not.**

The ratio is accidentally close to right: 3.7/2,100 = 0.176%, and the honest end-to-end figure is 4.9/2,823 = **0.17%**. But both terms were wrong, and they were wrong in ways that cancelled:

- **4.9 ms**, not 3.7 ms, for the vector search today (same method, different sample).
- **2,100 ms was never the pipeline.** It was the *retrieval stage*, taken from the broken-system trace. The real retrieval stage on a healthy system is **224 ms**, roughly 9x smaller. The real pipeline is **2,823 ms**.

Honest restatement, both denominators and both instances:

> **Local:** vector search is **4.9 ms of a 2,823 ms query (0.17%)**, and **2.2% of the 224 ms retrieval stage**.
> **Production:** vector search is **17.3 ms of a 2,189 ms query (0.8%)**, and **10.7% of the 161 ms retrieval stage**.
> On both, the retrieval stage is about 8% of the query and generation is about **92%**. Most of retrieval is the embedding API call, not the database.

Production is the number to quote in anything public, since it is what a user actually experiences. It is roughly 4x less favourable than the local figure, and the conclusion holds anyway.

Both denominators are worth stating because they answer different questions. Against the **pipeline**, the point is that a faster vector engine is invisible to the user: replacing pgvector with something infinitely fast would return 0.17% of the wait. Against the **retrieval stage**, the point is narrower but sharper: even inside the component named "retrieval", the database is 2% and the network call to OpenAI is 98%.

The engineering conclusion, that a faster vector engine would have optimised the wrong line, holds on both readings and is stronger than the original claim, because the true bottleneck (generation, 92%) is larger than the old broken denominator implied.

---

## Claims to restate wherever the old figure was quoted

1. "Vector search is 3.7 ms of a 2,100 ms pipeline" becomes the restated form above. Prefer the production figure: **17 ms of a 2,200 ms query, under 1%**.
2. "The retrieval stage came to about 2.1 seconds" is wrong by roughly 9x on a healthy system. It is 224 ms local, 161 ms production.
3. "The planner does not use the HNSW index" is confirmed on **both** local Postgres 17.10 and Neon 18.4, and is worth stating with the reason: forcing the index is 17x slower at this corpus size.

## How to reproduce

```
make db                       # Postgres + pgvector on :5433
PYTHONIOENCODING=utf-8 PYTHONPATH=. python docs/measurements/measure_pipeline.py
```

The script is committed next to this file. It spends real API budget: one embedding call per golden question plus 30 answers, which cost $0.0824 on this run.

Method, in full: connect timing over 5 fresh connections; KNN via `db.nearest(conn, stored_vector, k=5)`, 50 runs after 5 warm-ups, query vector read from a stored row so no embedding call is included; `embed_one` timed separately over the same 10 golden questions; end-to-end via `orchestrator.answer(conn, q, k=5)`, 10 questions x 3 rounds with the first call discarded as cold; `EXPLAIN (ANALYZE, BUFFERS)` on the exact `db.nearest` SQL, then repeated under `SET LOCAL enable_seqscan = off` as a session-local diagnostic that was rolled back.
