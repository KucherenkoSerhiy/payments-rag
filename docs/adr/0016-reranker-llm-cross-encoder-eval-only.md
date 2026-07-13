# 0016 - Reranking: LLM-as-cross-encoder, built for learning, kept eval-only

**Status:** Accepted 2026-07-09 - LLM-as-reranker retained as an eval/learning tool; the interactive path stays vector-default (consistent with ADR-0014).

## Context
ADR-0014 already *deprioritized* reranking for the product: the recall curve
plateaus at `@20 = 0.70`, so reranking (which only reorders what was fetched) has
a hard ceiling of +0.10 over the `0.60` baseline, not worth a new dependency for
a two-document corpus. That call stands.

The goal changed even though the product didn't: Track B (skill) wanted the
reranking *mechanism* hands-on, bi-encoder vs cross-encoder, fanout → rescore →
top-k. So we built it to learn it and to measure it against the golden set,
explicitly not as a product default.

## Decision
1. **Instantiate the cross-encoder as an LLM call rather than a local model.** The
   textbook cross-encoder is a local model (sentence-transformers / BGE-reranker)
   that scores query+passage pairs in a batched forward pass. We instead score
   each pair with a Haiku call returning a structured `relevance` 0-100
   (`adapters/reranker.py`). Rationale: avoid pulling a heavy ML stack (torch)
   into a learning exercise. The trade-off is latency (see Consequences).
2. **Keep it eval-only** (`retrieval_eval --rerank`), out of the interactive
   answer path. The orchestrator stays vector-default; this sits beside hybrid as
   an option, not a default.

## Measurement (2026-07-09)
`rerank recall@5 = 0.70`, up from vector `0.60`, and **exactly** the vector
`recall@20 = 0.70` ceiling. That equality is the real result: the cross-encoder
promoted *every fetchable relevant page* into the top-5, i.e. it did as well as
the fanout theoretically allows. The single rescued question is
`sct-inst-currency`, the same page hybrid rescued via keyword (ADR-0014), and the
same one that scored **0** in the M4 answer eval because the "euro" page never
reached the top-5. The other three misses (charging-principle, remittance-length,
value-limits) are never fetched even at 20, so they're recall-bound and untouchable
by reranking. Confirms ADR-0014's diagnosis: **the bottleneck is recall, not ranking.**

## Consequences / trade-offs
- **Latency is the blocker, and it's the point of the bi-vs-cross trade-off.** The
  eval took ~10 min: 10 questions × 20-candidate fanout = 200 *sequential* LLM
  calls. Per user question that's ~20 calls (~1 min naive), still too slow to
  serve interactively. Mitigations, in order of leverage: fire the fanout calls
  **concurrently** (→ ≈ one call's latency); shrink the fanout; or, the real fix,
  use a **local cross-encoder** that batches all candidates in tens of ms with
  no network. That last is *why* production rerankers are local models, not LLM
  APIs.
- **Cost:** ~20 Haiku calls per query, cheap in dollars; latency, not price, is
  what keeps it out of the interactive path.
- **If reranking ever earns a place in the product**, it's a local cross-encoder,
  not this LLM reranker. This ADR does not open that door; it records the lesson.

## Value
Not a product win (ADR-0014 already closed that). The value is Track B: the
reranking mechanism built and understood end-to-end, the +0.10 prediction
confirmed to the decimal, and the latency half of the bi-vs-cross trade-off felt
on real wall-clock instead of read in a doc.
