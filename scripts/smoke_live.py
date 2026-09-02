"""Pre-push smoke against the real DB + APIs (tests/test_smoke.py fakes the paid
services; this doesn't - hence scripts/, not tests/).

Run:  uv run python scripts/smoke_live.py    (exit 0 = healthy)
"""

from __future__ import annotations

from payments_rag.adapters import db
from payments_rag.answering.orchestrator import answer

BASELINE_Q = "How fast does an SCT Inst payment settle?"


def main() -> int:
    with db.connect() as conn:
        result = answer(conn, BASELINE_Q)
        ok = bool(result.answer) and len(result.citations) > 0
        print("OK" if ok else "FAIL", "-", result.answer[:80])
        return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
