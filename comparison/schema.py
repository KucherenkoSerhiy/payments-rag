"""Shared record every comparison adapter produces.

One shape for all three systems means scoring and reporting don't care which
system answered. `contexts` is always the full set the system actually
retrieved/consulted, not just what ended up cited, so RAGAS's context metrics
(precision, recall) mean the same thing across systems.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SystemAnswer:
    system: str          # e.g. "payments-rag", "openai-file-search", "haystack"
    question_id: str
    question: str
    answer: str
    contexts: list[str]   # passage texts the system actually consulted
    citations: list[str]  # human-readable citation strings; format varies by system
    ground_truth: str     # the golden-set expected answer, copied in for convenience
    latency_s: float
    cost_usd: float
    fidelity_note: str = ""  # e.g. "pasted extracted text, not native PDF upload"
    raw: dict = field(default_factory=dict)  # the system's raw response, for audit


def append_jsonl(path: Path, record: SystemAnswer) -> None:
    """Append one record. Called after every single question, not batched, so a
    crash mid-run loses at most one row, not the whole session."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[SystemAnswer]:
    records: list[SystemAnswer] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(SystemAnswer(**json.loads(line)))
    return records
