"""Integration test for the retrieval path — runs against the real Dockerized
Postgres+pgvector. Skips automatically if the DB isn't reachable, so the unit
suite still runs without Docker.

Deterministic and free: it uses hand-built unit vectors (no OpenAI calls). The
query vector is made *identical* to one stored chunk so its cosine distance is
0 — the global minimum — which makes the assertion robust even if the real
corpus is also indexed in the same table.
"""

from __future__ import annotations

import pytest

from payments_rag import config, db
from payments_rag.retriever import retrieve

TEST_SOURCE = "pytest-integration"


def _unit_vec(hot: int) -> list[float]:
    """A 1536-dim vector that is all zeros except a single 1.0 at index `hot`."""
    v = [0.0] * config.EMBED_DIM
    v[hot] = 1.0
    return v


@pytest.fixture
def conn():
    try:
        c = db.connect()
    except Exception:  # psycopg.OperationalError and friends
        pytest.skip("Postgres not reachable — run: docker compose -f infra/docker-compose.yml up -d")
    db.delete_source(c, TEST_SOURCE)
    c.commit()
    try:
        yield c
    finally:
        db.delete_source(c, TEST_SOURCE)
        c.commit()
        c.close()


def _seed(conn) -> None:
    for i in range(3):
        db.insert_chunk(
            conn,
            source=TEST_SOURCE,
            chunk_index=i,
            text=f"chunk about topic {i}",
            embedding=_unit_vec(i),
            page=i + 1,
        )
    conn.commit()


def test_nearest_returns_the_identical_vector_first(conn):
    _seed(conn)
    hits = db.nearest(conn, _unit_vec(1), k=1)  # exact match to chunk 1
    assert hits, "expected at least one hit"
    _id, source, text, page, distance = hits[0]
    assert source == TEST_SOURCE
    assert text == "chunk about topic 1"
    assert distance == pytest.approx(0.0, abs=1e-6)


def test_dimension_guard_rejects_wrong_size(conn):
    with pytest.raises(ValueError, match="dims"):
        db.insert_chunk(
            conn, source=TEST_SOURCE, chunk_index=0, text="x", embedding=[0.1, 0.2]
        )


def test_retrieve_wraps_rows_into_dataclass(conn, monkeypatch):
    _seed(conn)
    # Stub the embedding call so retrieve() needs no OpenAI key / network.
    monkeypatch.setattr("payments_rag.retriever.embed_one", lambda q: _unit_vec(2))
    results = retrieve(conn, "irrelevant question text", k=1)
    assert len(results) == 1
    top = results[0]
    assert top.source == TEST_SOURCE
    assert top.text == "chunk about topic 2"
    assert top.page == 3
    assert top.distance == pytest.approx(0.0, abs=1e-6)
