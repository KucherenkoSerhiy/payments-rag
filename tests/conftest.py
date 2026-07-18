"""Shared fixtures. `conn` gives a live DB connection or skips the test.

Everything run through it is rolled back on teardown, so DB tests can write
freely (e.g. wallet_guard spend) without polluting the local database.
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
        c.rollback()
        c.close()
