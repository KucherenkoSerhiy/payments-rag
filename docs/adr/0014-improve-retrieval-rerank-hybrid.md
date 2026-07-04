# 0014 — Improve retrieval quality (reranking and/or hybrid search)

**Status:** Proposed 2026-07-04 — to be finalized after M6 measurement

## Context
`recall@5 = 0.60` on the golden set. Because retrieval is the ceiling on answer
quality (generation can only use what it's handed — see ADR-0009 and the
ROADMAP note), the ~40% of questions whose answer page isn't in the top-5 get
weak or muddled answers. Concretely: "how fast does SCT Inst settle?" missed the
crisp "5 seconds" page (p26) because it never ranked into the top-5. We want to
raise recall without regressing cost/latency unacceptably.

## Decision (proposed)
Evaluate two **additive** techniques against the `recall@5` baseline and adopt
whichever moves the number (possibly both). Adopt nothing that doesn't.

1. **Reranking** — retrieve a wide net (top-N, e.g. 20–50 by vector distance),
   then a cross-encoder re-scores those for true relevance and keeps the final
   top-k. Directly targets the "right page ranked 6th+" case.
2. **Hybrid search** — combine vector similarity with keyword/BM25 (Postgres has
   full-text search built in), so exact terms like "maximum execution time" or
   "pacs.008" match even when the embedding blurs them.

## Alternatives
- **Just raise the final k** (hand the LLM more chunks). Rejected as the primary
  fix: it inflates prompt cost/latency and dilutes the context without improving
  *ranking* — the right page still isn't ranked well, just included among more noise.
- **Bigger embedding model** (`text-embedding-3-large`, ADR-0003) — complementary,
  a separate A/B.
- **Semantic chunking** — a different lever (chunk boundaries), also separate.

## Consequences / trade-offs to watch
- **Two different k's — don't conflate them.** The *retrieval fan-out* (widened,
  e.g. 20–50, internal to retrieval+rerank) is separate from the *final k* passed
  to the LLM (kept small, e.g. 5). Widening the fan-out costs an extra rerank
  step (latency/compute), **not** a bigger LLM prompt.
- **Any retrieval-pipeline change is user-visible** (latency, cost, and which
  passages appear). Measure `recall@5` before/after on the golden set; ship only
  what moves it (ADR-0009 discipline).
- **Likely a new dependency:** a reranker (local cross-encoder, or a hosted rerank
  API). Hybrid search via Postgres FTS adds *no* new dependency — a point in its favour.

## Measurement (2026-07-04 diagnostic)
Recall curve on the 10-question set: **@5 = 0.60, @10 = 0.70, @20 = 0.70**. It
plateaus at 20 → for 3/10 questions the right page isn't in the top-20 at all.
Reranking only reorders retrieved candidates, so its ceiling here is recall@20 =
0.70 (max +0.10 over the current 0.60). **The bottleneck is recall, not ranking.**
Implication: try **hybrid search (vector + BM25)** first — it can pull the
missing exact-term pages into the candidate set; reranking is a secondary,
lower-headroom lever. (Small sample — directional; grow the golden set for
stable numbers.)

## Decision gate
Finalize this ADR (Accepted, naming the concrete choice) only after measuring the
candidates against the golden set. Until then, this records the direction, not a
committed technique. Current lean from the diagnostic: **hybrid first**.
