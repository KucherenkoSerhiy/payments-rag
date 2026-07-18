-- Runs once on first container start (docker-entrypoint-initdb.d).
-- Embedding dimension 1536 matches text-embedding-3-small (pinned; changing it
-- invalidates every stored vector, so re-index from scratch).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT        NOT NULL,   -- the source PDF's file name
    page        INTEGER,                -- 1-based page number, null if not paged
    chunk_index INTEGER     NOT NULL,   -- order within the source
    text        TEXT        NOT NULL,
    embedding   VECTOR(1536) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Approximate nearest-neighbour index for cosine distance.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- Full-text (keyword) index for hybrid search: lexical ranking to complement
-- the semantic vector search. English config matches the corpus language.
CREATE INDEX IF NOT EXISTS chunks_text_fts_idx
    ON chunks USING gin (to_tsvector('english', text));

-- Wallet guard spend ledger (api/guard.py): one row per UTC day. The app also
-- self-heals a missing table on first use; kept here so a fresh DB is
-- complete from init. Keep both definitions in sync.
CREATE TABLE IF NOT EXISTS wallet_guard (
    day       DATE           PRIMARY KEY,
    spent_usd NUMERIC(10, 6) NOT NULL DEFAULT 0
);
