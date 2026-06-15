"""Spike step 4 — one PDF page through the whole pipeline.

read PDF page -> extract text -> chunk -> embed -> store -> retrieve.

Usage:
    uv run python -m spike.step4_pdf path/to/sepa.pdf [page] [-- "your question"]

`page` is 1-based and defaults to 1. Drop a real SEPA / ISO 20022 PDF into
corpus/raw/ and point this at it. The corpus is intentionally not committed.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader

from payments_rag import db
from payments_rag.chunker import chunk_text
from payments_rag.embedding import embed, embed_one
from spike._log import setup

log = setup()

SOURCE_PREFIX = "spike-step4"


def parse_args(argv: list[str]) -> tuple[Path, int, str | None]:
    if not argv:
        raise SystemExit(
            "usage: uv run python -m spike.step4_pdf <pdf> [page] [-- question]\n"
            "Drop a SEPA PDF in corpus/raw/ and pass its path."
        )
    pdf = Path(argv[0])
    if not pdf.is_file():
        raise SystemExit(f"file not found: {pdf}")

    page = 1
    question: str | None = None
    rest = argv[1:]
    if "--" in rest:
        i = rest.index("--")
        question = " ".join(rest[i + 1 :]).strip() or None
        rest = rest[:i]
    if rest:
        page = int(rest[0])
    return pdf, page, question


def main(argv: list[str] | None = None) -> None:
    pdf_path, page_no, question = parse_args(argv if argv is not None else sys.argv[1:])

    reader = PdfReader(str(pdf_path))
    if not 1 <= page_no <= len(reader.pages):
        raise SystemExit(f"page {page_no} out of range (1..{len(reader.pages)})")

    text = reader.pages[page_no - 1].extract_text() or ""
    log.info("read %s page %d/%d: %d chars", pdf_path.name, page_no, len(reader.pages), len(text))
    if not text.strip():
        raise SystemExit("no extractable text on that page (scanned image? try another page)")

    chunks = chunk_text(text, size=120, overlap=20)
    log.info("chunked into %d pieces", len(chunks))

    source = f"{SOURCE_PREFIX}:{pdf_path.name}#p{page_no}"
    with db.connect() as conn:
        db.delete_source(conn, source)  # idempotent
        vectors = embed(chunks)
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            db.insert_chunk(
                conn, source=source, page=page_no, chunk_index=i, text=chunk, embedding=vec
            )
        conn.commit()
        log.info("embedded + stored %d chunks", len(chunks))

        q = question or "What is this page about?"
        results = db.nearest(conn, embed_one(q), k=3)
        log.info("query: %s", q)
        for rank, (cid, _src, ctext, pg, dist) in enumerate(results, 1):
            preview = ctext.replace("\n", " ")[:140]
            log.info("  #%d  dist=%.4f  p%s  %s ...", rank, dist, pg, preview)

    log.info("STEP 4 OK — PDF page traversed the full pipeline")


if __name__ == "__main__":
    main()
