"""Shared piece of both scorers' resumable caches.

Each scorer keeps its own content-hash function on purpose (RAGAS hashes
answer+contexts, the judge hashes the answer alone) and those must stay
byte-stable or every cached row re-grades at real API cost.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_existing(path: Path) -> dict[tuple[str, str], dict]:
    """Prior scored rows keyed by (system, question_id); empty if no prior run."""
    if not path.exists():
        return {}
    existing = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        existing[(row["system"], row["question_id"])] = row
    return existing
