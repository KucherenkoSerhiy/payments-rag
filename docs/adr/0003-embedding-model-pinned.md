# 0003 - Embeddings: `text-embedding-3-small`, pinned

**Status:** Accepted (2026-06, scoping v1)

## Context
The embedding model is the keystone shared by indexing and query. The same
model must produce both the stored chunk vectors and the query vector, or the
vectors are not comparable. Its dimension (1536) is baked into the DB schema
(`VECTOR(1536)`).

## Decision
Use OpenAI `text-embedding-3-small` (1536 dims), pinned explicitly in config and
enforced at insert (`EMBED_DIM` guard in `db.insert_chunk`).

## Alternatives
- **`text-embedding-3-large`** (3072 dims). Better retrieval quality, ~6.5×
  cost, and a schema change + full re-embed. Kept as the A/B lever for when evals
  can measure whether the quality gain is real. `-large` can also be truncated to
  1536 dims to keep the schema, which is a cheap upgrade path.
- **Local `sentence-transformers`**. Free, offline (relevant to the on-prem value
  prop), but lower quality and pulls in torch. Deferred to a Phase-2 on-prem story.

## Consequences
- Cheap, high-quality embeddings; corpus indexes for pennies.
- **Changing the model invalidates every stored vector**, meaning a full
  re-embed. The dimension guard makes a mismatched model fail fast instead of
  silently.
- Embedding choice gates retrieval quality more than the LLM choice does, so this
  is the higher-leverage knob to tune later.
