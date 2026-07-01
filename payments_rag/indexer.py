"""Corpus indexer: PDF files -> chunks -> embeddings -> pgvector.

Productionizes spike/step4 into a reusable, idempotent pipeline:
- chunks are made **per page** so the stored page number is exact (needed for
  citations later); the cross-page context loss this causes is the known
  chunking-quality tradeoff, deferred until retrieval is measurable.
- embeddings are sent in batches (one API call per ~100 chunks, not per chunk).
- re-indexing a document replaces its rows (delete-by-source), so runs are safe
  to repeat.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pypdf import PdfReader

from payments_rag import db
from payments_rag.chunker import chunk_text
from payments_rag.embedding import embed

logger = logging.getLogger(__name__)

EMBED_BATCH = 100  # chunks per embedding API call

# Synthetic spike fixture — not part of the real corpus, skip it when indexing.
_FIXTURE_NAMES = {"sample_sepa.pdf"}


@dataclass
class IndexStats:
    source: str
    pages: int
    pages_with_text: int
    chunks: int


def _extract_chunks(
    path: Path, *, chunk_size: int, overlap: int
) -> tuple[int, int, list[tuple[int, str]]]:
    """Return (total_pages, pages_with_text, [(page_number, chunk_text), ...])."""
    reader = PdfReader(str(path))
    records: list[tuple[int, str]] = []
    pages_with_text = 0
    for page_no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue  # blank / image-only page
        pages_with_text += 1
        for chunk in chunk_text(text, size=chunk_size, overlap=overlap):
            records.append((page_no, chunk))
    return len(reader.pages), pages_with_text, records


def index_pdf(
    conn: psycopg.Connection,
    path: str | Path,
    *,
    chunk_size: int = 300,
    overlap: int = 50,
) -> IndexStats:
    """Index a single PDF into pgvector. Replaces any existing rows for it."""
    path = Path(path)
    source = path.name
    total_pages, pages_with_text, records = _extract_chunks(
        path, chunk_size=chunk_size, overlap=overlap
    )

    db.delete_source(conn, source)  # idempotent reindex

    texts = [text for _, text in records]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        vectors.extend(embed(batch))
        logger.info("  %s: embedded %d/%d chunks", source, len(vectors), len(texts))

    for chunk_index, ((page_no, text), vec) in enumerate(zip(records, vectors)):
        db.insert_chunk(
            conn,
            source=source,
            page=page_no,
            chunk_index=chunk_index,
            text=text,
            embedding=vec,
        )
    conn.commit()

    stats = IndexStats(source, total_pages, pages_with_text, len(records))
    logger.info(
        "indexed %s: %d pages (%d with text) -> %d chunks",
        source,
        total_pages,
        pages_with_text,
        len(records),
    )
    return stats


def index_corpus(
    conn: psycopg.Connection,
    corpus_dir: str | Path = "corpus/raw",
    *,
    chunk_size: int = 300,
    overlap: int = 50,
) -> list[IndexStats]:
    """Index every real PDF in a directory (skips the synthetic spike fixture)."""
    corpus_dir = Path(corpus_dir)
    pdfs = sorted(p for p in corpus_dir.glob("*.pdf") if p.name not in _FIXTURE_NAMES)
    if not pdfs:
        raise SystemExit(f"no corpus PDFs found in {corpus_dir}")
    return [
        index_pdf(conn, p, chunk_size=chunk_size, overlap=overlap) for p in pdfs
    ]
