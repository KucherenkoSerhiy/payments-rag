"""Postgres + pgvector access helpers.

Thin wrapper over psycopg. No ORM (raw SQL is legible and the schema is tiny).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import psycopg
from pgvector.psycopg import register_vector

from payments_rag import config

logger = logging.getLogger(__name__)


def connect() -> psycopg.Connection:
    """Open a connection with the pgvector type adapter registered."""
    conn = psycopg.connect(config.DATABASE_URL, connect_timeout=config.DB_CONNECT_TIMEOUT)
    register_vector(conn)
    return conn


def _vec(values: Sequence[float]) -> str:
    """Format a float sequence as a pgvector literal, e.g. '[0.1,0.2,0.3]'.

    Passed as text and cast with `::vector` in SQL. A bare Python list is sent
    as `double precision[]`, which the `<=>` operator does not accept; the
    literal + cast is unambiguous for both inserts and similarity queries.
    """
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def insert_chunk(
    conn: psycopg.Connection,
    *,
    source: str,
    chunk_index: int,
    text: str,
    embedding: Sequence[float],
    page: int | None = None,
) -> int:
    """Insert one chunk + embedding, return its id."""
    if len(embedding) != config.EMBED_DIM:
        raise ValueError(
            f"embedding has {len(embedding)} dims, expected {config.EMBED_DIM} "
            f"({config.EMBED_MODEL}); chunks.embedding is VECTOR({config.EMBED_DIM}). "
            "Changing the embedding model needs a schema change + full re-embed."
        )
    row = conn.execute(
        """
        INSERT INTO chunks (source, page, chunk_index, text, embedding)
        VALUES (%s, %s, %s, %s, %s::vector)
        RETURNING id
        """,
        (source, page, chunk_index, text, _vec(embedding)),
    ).fetchone()
    assert row is not None
    return int(row[0])


def nearest(
    conn: psycopg.Connection,
    query_embedding: Sequence[float],
    *,
    k: int = 3,
) -> list[tuple[int, str, str, int | None, float]]:
    """Return the k nearest chunks as (id, source, text, page, distance).

    Distance is cosine distance (0 = identical, 2 = opposite). `<=>` is the
    pgvector cosine-distance operator.
    """
    rows = conn.execute(
        """
        SELECT id, source, text, page, embedding <=> %s::vector AS distance
        FROM chunks
        ORDER BY distance ASC
        LIMIT %s
        """,
        (_vec(query_embedding), k),
    ).fetchall()
    return [(int(r[0]), r[1], r[2], r[3], float(r[4])) for r in rows]


def delete_source(conn: psycopg.Connection, source: str) -> int:
    """Remove all chunks for a source (so re-indexing a document stays idempotent)."""
    cur = conn.execute("DELETE FROM chunks WHERE source = %s", (source,))
    return cur.rowcount


def count(conn: psycopg.Connection) -> int:
    row = conn.execute("SELECT count(*) FROM chunks").fetchone()
    assert row is not None
    return int(row[0])


def clear_all(conn: psycopg.Connection) -> int:
    """Delete every chunk (e.g. to drop stale data before a clean re-index)."""
    cur = conn.execute("DELETE FROM chunks")
    return cur.rowcount


def source_counts(conn: psycopg.Connection) -> list[tuple[str, int]]:
    """Return (source, chunk_count) per source, most chunks first."""
    rows = conn.execute(
        "SELECT source, count(*) FROM chunks GROUP BY source ORDER BY count(*) DESC"
    ).fetchall()
    return [(r[0], int(r[1])) for r in rows]


def keyword_search(
    conn: psycopg.Connection, query_text: str, *, k: int = 20
) -> list[tuple[int, str, str, int | None, float]]:
    """Full-text keyword search: the k best chunks by lexical relevance.

    Complements `nearest` (semantic). The query's salient terms are OR-ed, not
    AND-ed: a natural-language question shares only some words with a terse spec
    passage, so requiring every word (AND) matches nothing. OR-ing lets a chunk
    match on ANY term and `ts_rank` rewards those covering more of them. Returns
    (id, source, text, page, rank), best first.

    Implementation: plainto_tsquery already stems + drops stopwords and joins
    terms with `&`; we rewrite `&` -> `|` to turn the AND into an OR.
    """
    rows = conn.execute(
        """
        WITH q AS (
            SELECT replace(plainto_tsquery('english', %s)::text, '&', '|')::tsquery AS query
        )
        SELECT c.id, c.source, c.text, c.page,
               ts_rank(to_tsvector('english', c.text), q.query) AS rank
        FROM chunks c, q
        WHERE to_tsvector('english', c.text) @@ q.query
        ORDER BY rank DESC
        LIMIT %s
        """,
        (query_text, k),
    ).fetchall()
    return [(int(r[0]), r[1], r[2], r[3], float(r[4])) for r in rows]
