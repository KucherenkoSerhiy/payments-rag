# Retrieval Quality Playbook

Guidance for the "make the answers actually good" work: how to diagnose where
retrieval is losing recall, and the ranked stack of fixes to reach for. See also
ADR-0014 (retrieval levers), ADR-0009 (measure-before-ship discipline), and
`docs/glossary.md`.

## The diagnosis (data-grounded, 2026-07-10)

Answers dodge specifics ("settles instantly, see section 4.2.3" instead of
"5 seconds") **not** because the fact is missing from the corpus, but because the
answer page is **retrieved yet ranked below the top-5 the LLM sees.**

Retrieval trace (`retrieve(..., k=10)`), gold page in brackets:

| question phrasing | gold page rank |
|---|---|
| "target maximum execution time" (formal, page's words) | **1** |
| "how fast does an SCT Inst payment settle?" (casual) | **9** |
| "does the scheme set a maximum amount?" (value-limits) | **8** |

The *same* p26 ("5 seconds") ranks 1st for the page's wording and 9th for a
user's wording. Two compounding causes:

1. **Query ↔ page vocabulary gap.** A casual question embeds far from formal spec
   prose.
2. **Coarse per-page chunks (ADR-0008).** A page's embedding is an *average* of
   everything on it, so a single fact competes with the whole page and ranks on
   broad similarity, not fact similarity.

**It is a ranking / matching problem, not coverage.** Reranking and hybrid only
*reorder what was fetched*; they cannot recover signal that was averaged away at
index time.

## The fix stack (OSS consensus, ranked by leverage for us)

1. **Contextual Retrieval (Anthropic).** Before embedding each chunk, have Claude
   write a 50–100 token blurb of what the chunk is (given the whole doc) and
   prepend it. A bare "5 seconds" chunk becomes findable. Reported up to **49%**
   fewer failed retrievals (embeddings + BM25), **67%** with reranking. Attacks
   *both* causes; on-brand for our stack. Cost: a one-time re-index (an LLM call
   per chunk).
2. **Small-to-big / sentence-window chunking.** Stop embedding whole pages —
   embed sentences, retrieve those, feed the LLM the surrounding parent. Fixes
   dilution at the root, and *reconciles with why we chose per-page* (citation
   accuracy): retrieve small for precision, cite the parent page for verifiability.
   Revisits ADR-0008.
3. **Multi-query / RAG-Fusion.** Rewrite the question into 3–6 variants, retrieve
   each, **fuse with the RRF we already wrote.** Cheap, non-fabricating, directly
   closes the vocabulary gap (would lift p26 from rank 9 to the fused top-5).
4. **Reranking (cross-encoder).** The consistent benchmark winner; stacks on the
   above. Built already (`retrieval/rerank.py`), eval-only on latency grounds.

## What NOT to do

- **HyDE** (embed a hypothetical answer). OSS guidance: avoid for compliance-heavy
  domains — a hallucinated draft misleads retrieval. Payments specs qualify. We
  removed the paused HyDE scaffold for this reason.
- **Just raise k.** Dilutes the prompt with noise without fixing ranking (ADR-0014).

## Our plan (cheap → structural)

1. **Multi-query / RAG-Fusion first** — reuses the RRF, cheap, non-fabricating,
   and we'll *see* p26 climb in the Evals page (recall@k live).
2. **Contextual Retrieval** — the biggest single lever; a re-index pass.
3. **Small-to-big chunking** — the deeper structural variant, if 1–2 don't get us
   there.

## Discipline

Measure every change on the golden set (recall@k) before/after; ship only what
moves the number (ADR-0009). The Evals page makes this a one-click check.

## Sources

- Anthropic — Contextual Retrieval: https://www.anthropic.com/engineering/contextual-retrieval
- LlamaIndex small-to-big: https://medium.com/data-science/advanced-rag-01-small-to-big-retrieval-172181b396d4
- Parent-document retrieval: https://zeroentropy.dev/concepts/parent-document-retrieval/
- Haystack query expansion: https://haystack.deepset.ai/blog/query-expansion
- Beyond the Reranker (arXiv): https://arxiv.org/html/2606.28367v1
