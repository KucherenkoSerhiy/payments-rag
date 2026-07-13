"""Smoke test: does the whole thing start and answer one question end-to-end?

Run before pushing:  python -m smoke_test
Exit 0 = healthy, 1 = broken. Hits the real DB + APIs (not a unit test).
"""

from __future__ import annotations

from payments_rag.adapters import db
from payments_rag.orchestrator import answer

BASELINE_Q = "How fast does an SCT Inst payment settle?"


def main() -> int:
    with db.connect() as conn:
        result = answer(conn, BASELINE_Q)
        ok = bool(result.answer) and len(result.citations) > 0
        print("OK" if ok else "FAIL", "-", result.answer[:80])
        return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
