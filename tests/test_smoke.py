"""End-to-end smoke: index a sample PDF, ask a question, expect a cited answer.

This is the happy-path check behind `make smoke` and the CI smoke step. It runs
the *real* pipeline (PDF parsing, chunking, pgvector store + search, citation
mapping) but fakes the two paid services (embeddings, LLM), so it needs a running
Postgres but no API keys. That makes it safe to run on every push.

The sample PDF is generated here (a few lines of SEPA-flavoured text) rather than
checked in as a binary, so the fixture is transparent and reproducible.
"""

from __future__ import annotations

import hashlib
import random
import re
from pathlib import Path

import pytest

from payments_rag import config
from payments_rag.adapters import db
from payments_rag.indexing.indexer import CorpusIndexer
from payments_rag.orchestrator import answer

SAMPLE_NAME = "smoke_sample.pdf"
SAMPLE_LINES = [
    "SEPA Instant Credit Transfer (SCT Inst) rulebook, smoke sample.",
    "The maximum execution time for an SCT Inst payment is 5 seconds.",
    "The scheme is available 24 hours a day on all calendar days of the year.",
    "SCT Inst payments are executed in euro.",
]


def _fake_vec(text: str) -> list[float]:
    """A deterministic unit-ish vector for `text`. Stands in for a real embedding."""
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    rnd = random.Random(seed)
    return [rnd.uniform(-1.0, 1.0) for _ in range(config.EMBED_DIM)]


# One fixed vector shared by the sample's chunks and the query. The query then
# matches the sample at cosine distance 0 and outranks anything else already in
# the table (a real embedding never collides with this), so the smoke is
# deterministic regardless of what else happens to be indexed locally.
_ANCHOR = _fake_vec("payments-rag-smoke-anchor")


def _fake_complete_json(prompt: str):
    """Stand-in LLM: cite the first chunk id the prompt offers, return canned text."""
    match = re.search(r"\[chunk (\d+)\]", prompt)
    citations = [int(match.group(1))] if match else []
    data = {"answer": "An SCT Inst payment settles in about 5 seconds (smoke).", "citations": citations}
    usage = {"input_tokens": 1, "output_tokens": 1}
    return data, usage


def _write_sample_pdf(path: Path, lines: list[str]) -> None:
    """Write a minimal one-page PDF whose text pypdf can extract (stdlib only)."""
    ops = "BT /F1 12 Tf 72 720 Td 14 TL\n"
    for line in lines:
        esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops += f"({esc}) Tj T*\n"
    ops += "ET"
    content = ops.encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    path.write_bytes(out)


@pytest.fixture
def conn():
    try:
        c = db.connect()
    except Exception:  # psycopg.OperationalError and friends
        pytest.skip("Postgres not reachable; run: make db")
    db.delete_source(c, SAMPLE_NAME)
    c.commit()
    try:
        yield c
    finally:
        db.delete_source(c, SAMPLE_NAME)
        c.commit()
        c.close()


def test_smoke_index_and_answer(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "payments_rag.indexing.indexer.embed", lambda texts: [list(_ANCHOR) for _ in texts]
    )
    monkeypatch.setattr("payments_rag.retrieval.retriever.embed_one", lambda text: list(_ANCHOR))
    monkeypatch.setattr("payments_rag.adapters.llm.complete_json", _fake_complete_json)

    pdf = tmp_path / SAMPLE_NAME
    _write_sample_pdf(pdf, SAMPLE_LINES)

    stats = CorpusIndexer(conn).index_pdf(pdf)
    assert stats.chunks > 0, "sample PDF produced no chunks (text not extracted?)"

    result = answer(conn, "How fast does an SCT Inst payment settle?")

    assert result.answer.strip(), "expected a non-empty answer"
    assert result.citations, "expected at least one citation"
    assert result.citations[0].source == SAMPLE_NAME
    assert result.citations[0].page == 1
