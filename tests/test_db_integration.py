"""DB integration test: verifies the real Postgres + pgvector path (read-only).

Runs against the pgvector service in CI and a local DB in dev; a fresh clone with
no database simply skips. Strictly read-only; it never mutates the corpus.
"""

from __future__ import annotations

import pytest

from payments_rag.adapters import db


@pytest.fixture
def conn():
    try:
        c = db.connect()
    except Exception as exc:  # no DB reachable (e.g. a fresh clone)
        pytest.skip(f"no database available: {exc}")
    try:
        yield c
    finally:
        c.close()


def test_connectivity(conn):
    assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_pgvector_extension_installed(conn):
    row = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()
    assert row is not None, "pgvector extension is not installed"


def test_chunks_table_and_cosine_operator(conn):
    # exercises the chunks table + the <=> cosine operator; works empty or populated
    conn.execute("SELECT id, embedding <=> embedding FROM chunks LIMIT 1").fetchall()
