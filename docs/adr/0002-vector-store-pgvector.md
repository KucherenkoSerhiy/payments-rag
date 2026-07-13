# 0002 - Vector store: Postgres + pgvector

**Status:** Accepted (2026-06, scoping v1)

## Context
Retrieval needs fast nearest-neighbour search over embedding vectors. The corpus
is small (≤ ~1M vectors; today ~500 chunks).

## Decision
Store vectors in Postgres via the `pgvector` extension. Same database holds the
chunk text, source metadata, and the vector in one row.

## Alternatives
- **Dedicated vector DBs** (Chroma, Qdrant, Pinecone). More specialised ANN
  features, but that's a new technology to learn and operate, and Pinecone adds a
  hosted dependency + cost.
- pgvector is "good enough" to ~1M vectors, reuses existing Postgres skill, and
  keeps text + metadata + vector transactional in one store.

## Consequences
- One container, one query language (SQL); citations join trivially to the text.
- Two index choices exist: HNSW (chosen: no training, incremental inserts, best
  recall/speed, more memory) vs IVFFlat (needs a representative set to train,
  cheaper memory). HNSW suits a small, growing corpus.
- If the corpus ever outgrows pgvector, this ADR gets superseded. The retriever
  interface (`db.nearest`) is the seam that would change.
