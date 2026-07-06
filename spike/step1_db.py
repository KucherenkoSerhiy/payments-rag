"""Spike step 1 — Postgres + pgvector is up and a SQL/vector session works.

Proves: connection, the `vector` extension is loaded, the `chunks` table from
init.sql exists, and a cosine-distance computation runs server-side.
"""

from __future__ import annotations

from pgvector.psycopg import register_vector

from payments_rag.adapters import db
from spike._log import setup

log = setup()


def main() -> None:
    with db.connect() as conn:
        register_vector(conn)

        version = conn.execute("SELECT version()").fetchone()[0]
        log.info("connected: %s", version.split(",")[0])

        ext = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        if ext is None:
            raise SystemExit("pgvector extension not installed — check init.sql")
        log.info("pgvector extension version %s", ext[0])

        # Table from init.sql present?
        cols = conn.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_name = 'chunks'"
        ).fetchone()[0]
        log.info("chunks table has %s columns", cols)

        # Server-side cosine distance between two vectors.
        dist = conn.execute(
            "SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector"
        ).fetchone()[0]
        log.info("cosine distance [1,0,0] <=> [0,1,0] = %s (expect 1.0)", dist)

    log.info("STEP 1 OK — Postgres + pgvector verified")


if __name__ == "__main__":
    main()
