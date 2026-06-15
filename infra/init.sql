-- Runs once on first container start (docker-entrypoint-initdb.d).
-- Embedding dimension 1536 matches text-embedding-3-small (pinned in scoping.md).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT        NOT NULL,   -- e.g. file name or "spike"
    page        INTEGER,                -- 1-based page number, null if not paged
    chunk_index INTEGER     NOT NULL,   -- order within the source
    text        TEXT        NOT NULL,
    embedding   VECTOR(1536) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Approximate nearest-neighbour index for cosine distance.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
