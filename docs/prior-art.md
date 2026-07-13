# Prior art — libraries for what we hand-rolled

We built retrieval, fusion, and evaluation from scratch on purpose (learning; see
ADR-0004). Almost every piece has a mature open-source equivalent. This is the
off-ramp: **if retrieval quality becomes a real bottleneck or the corpus grows,
revisit these** instead of hand-tuning. Recorded 2026-07 after M6.

## What we built → what to reach for

| We hand-rolled | Standard library / tool | Notes |
|---|---|---|
| `reciprocal_rank_fusion` + `recall_at_k`/`hit_at_k` | **[`ranx`](https://github.com/AmenRa/ranx)** | Does *both*: fusion (RRF + others, score normalization, auto-weight-optimization) **and** IR metrics (recall@k, MRR, MAP, nDCG, hit-rate @1/3/5/10, significance tests). Numba-accelerated. Our code is a tiny slice of it. |
| (didn't build) reranking — the +0.10 lever | **`sentence-transformers` CrossEncoder** + **`BAAI/bge-reranker-v2-m3`** | Best open-weight reranker (~278M params, CPU-OK for small batches). Swap backends via a `rerankers`-style interface; `FlashRank` for a light option. Cohere Rerank = hosted equivalent. |
| pgvector + Postgres FTS (our hybrid hack) | Native hybrid in **Qdrant / Weaviate / Elasticsearch / Milvus** | Sparse BM25 + dense vector in one system, RRF built in. Weaviate `alpha` knob (0=keyword…1=vector); Qdrant `Fusion.RRF` / `DBSF`. |
| `ts_rank` (TF-IDF-ish, not real BM25) | **ParadeDB / `pg_search`** | Real BM25 *inside Postgres* if we want to stay on one DB. |
| answer-quality eval | **RAGAS** | RAG-specific: faithfulness, answer-relevancy, context metrics. The answer-side analog of `ranx`. |
| the whole loop | LlamaIndex / Haystack | Bundle retrievers, `QueryFusionRetriever` (RRF), reranker post-processors. (Scoping keeps our core framework-free — ADR-0004.) |

## Why our M6 result was neutral (and the approach still sound)
The literature reports large hybrid gains on real corpora — e.g. BM25+vector
≈ **91% recall@10** vs 78% dense-only / 65% sparse-only. Our neutral result
(0.60 = 0.60) is a **corpus artifact**: 2 documents / 10 questions is too small
and homogeneous to surface the exact-term misses hybrid rescues. The technique is
right; the test corpus couldn't show it.

## When to revisit
- Corpus grows to many documents / a real user workload (hybrid + reranking start
  paying off — that 91% figure is the target).
- `recall@k` stays low **and** it's hurting answer quality that users notice.
- A keyword-heavy workload appears (exact codes/terms) — reranking + real BM25.

At that point the production shape is well-trodden: a vector DB with native hybrid
+ a BGE cross-encoder reranker + `ranx`/RAGAS for evaluation.

## References
- ranx — <https://github.com/AmenRa/ranx>
- Best reranker models 2026 — <https://docs.bswen.com/blog/2026-02-25-best-reranker-models/>
- Reranking / cross-encoders guide — <https://localaimaster.com/blog/reranking-cross-encoders-guide>
- Hybrid search reference 2026 — <https://www.digitalapplied.com/blog/hybrid-search-bm25-vector-reranking-reference-2026>
- Weaviate hybrid search — <https://weaviate.io/blog/hybrid-search-explained>
- Qdrant hybrid search — <https://qdrant.tech/articles/hybrid-search/>
