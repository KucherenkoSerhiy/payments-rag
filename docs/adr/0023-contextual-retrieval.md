# ADR-0023: Contextual Retrieval

Date: 2026-09-02
Status: accepted (indexing feature behind `cli index --contextual`; local/dev
index measured below; re-indexing the production Neon DB is a separate,
deliberate step)

## Context

Multi-query retrieval (ADR-0022) proved the vocabulary gap is real but left
recall@5 at the 0.60 baseline: rewriting the question cannot help when the
fact's chunk embeds as an average of everything around it. The
retrieval-quality playbook ranks Contextual Retrieval (Anthropic) first by
leverage precisely because it attacks that dilution at index time: before
embedding each chunk, an LLM writes a short blurb situating it ("SCT Inst
rulebook, target maximum execution time...") and the blurb+chunk embeds
together, so a bare "5 seconds" becomes findable from a casual question.

## Decision

- `adapters/contextualizer.py`: one ~150-word summary per document, then one
  Haiku call per page contextualizes all of that page's chunks (JSON array
  out, temperature 0). Batching per page keeps the one-time cost ~$0.5 for
  this corpus instead of the naive per-chunk-with-full-document approach.
- `CorpusIndexer(contextual=True)` / `cli index --contextual`: the blurb is
  prepended to the chunk **for embedding only**. The stored `text` column -
  what gets cited, shown as evidence, and keyword-searched - stays the
  verbatim spec passage (ADR-0006). No schema change; a plain re-index fully
  reverts the feature.
- A failed blurb call degrades that page to bare-chunk embedding with a
  warning; contextualization is an optimization, never a dependency.

## Measured result (2026-09-02, 10-question golden set, local index)

| mode | recall@5 |
|---|---|
| vector, plain index (baseline) | 0.60 |
| **vector, contextual index** | **0.80** |
| multi-query, contextual index | 0.80 (different hit profile, no net gain) |

The +0.20 is strictly additive: every baseline hit is kept, and the two new
hits are `sct-inst-currency` - the retrieval miss behind the system's only
judge-0 answer - and `sct-value-limits`. End-to-end confirmation: asked live
against the contextual index, the currency question now answers "SCT Inst
payments are made in euro" (previously it dodged the fact and scored 0).
Contextualization succeeded for all 484 chunks (zero fallback pages); the
one-time indexing cost was ~$0.5 and query-time cost/latency are unchanged -
which beats the reranker's 0.70 (ADR-0016) that costs ~1 min per query.
Multi-query stacked on top only reshuffles hits (gains remittance-length,
drops max-execution-time), consistent with ADR-0022's verdict.

## Consequences

- The local/dev index is contextual after this change; re-running
  `cli index --reset` without the flag restores plain embeddings exactly.
- The production Neon index is untouched until someone runs the contextual
  index against it - that promotion decision belongs with the measured
  numbers above.
- Re-collecting `compare-payments-rag` against a contextual index would
  change the comparison data; the published comparison numbers were measured
  against the plain index.
