# ADR-0022: Multi-query retrieval, eval-first

Date: 2026-09-02
Status: accepted (eval-only; promoting it into the live /ask path is a separate
decision gated on the recall numbers below)

## Context

Retrieval recall is the measured bottleneck (recall@5 = 0.60): the answer page
is usually *fetched* but ranked below the top-5 the LLM sees, because casual
question wording embeds far from formal rulebook prose (the playbook's p26
trace: rank 1 for the spec's own wording, rank 9 for "how fast does an SCT Inst
payment settle?"). The retrieval-quality playbook ranks multi-query third by
leverage but first by cost: it needs no re-indexing, reuses the RRF fusion
hybrid retrieval already has, and cannot inject non-corpus text into the
prompt (unlike HyDE, which the playbook bans for this domain).

## Decision

- `adapters/query_rewriter.py`: one Haiku call turns the question into up to 3
  spec-vocabulary rephrasings (~$0.0001, ~1s).
- `retrieval/multi_query.py::retrieve_multi`: retrieve a 10-wide list per
  phrasing (original always included), fuse with `reciprocal_rank_fusion`,
  return top-k. A rewriter failure degrades to plain single-query retrieval.
- Exposed only as `evals.retrieval_eval --multi-query`; the production path is
  unchanged, per the measure-before-ship discipline (ADR-0009) that kept
  reranking eval-only (ADR-0016).

## Measured result (2026-09-02, 10-question golden set)

| mode | recall@5 |
|---|---|
| vector (baseline) | 0.60 |
| multi-query, default temperature, run 1 | 0.50 |
| multi-query, default temperature, run 2 | 0.70 |
| multi-query, temperature 0, runs 3+4 | 0.60 (stable) |

Two findings, neither the hoped-for lift:

1. **At default temperature the mode is a dice roll** (0.50-0.70 across
   identical runs): nondeterministic rewrites make recall irreproducible.
   Fixed by pinning `temperature=0` in the rewriter - a requirement for any
   retrieval mode regardless of score.
2. **At temperature 0, aggregate recall is unchanged (0.60 = baseline) but the
   hit profile shifts**: multi-query gains `sct-inst-currency` - the one
   question whose retrieval miss produces the system's only judge-0 answer -
   and loses `sct-recall-deadlines`, which the baseline answers well. A
   one-for-one trade, not a win.

## Verdict

**Not shipped.** The vocabulary gap is real (the currency gain proves rewrites
find pages casual phrasing misses), but rewriting alone cannot overcome the
coarse-chunk dilution the playbook names as the second cause - a fact competes
with everything else averaged into its ~300-word chunk no matter how the
question is phrased. This matches the playbook's own ranking: the fixes that
attack dilution (contextual retrieval, sentence-window chunking) are the
higher-leverage moves; multi-query may still earn its place stacked on top of
them. No further parameter tuning against this 10-question set - chasing +0.10
on n=10 is overfitting, per the project's own eval discipline.

The mode stays available as `evals.retrieval_eval --multi-query` for re-running
after an indexing-side fix lands.
