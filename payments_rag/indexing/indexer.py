"""Corpus indexer: PDF files -> chunks -> embeddings -> pgvector.

`CorpusIndexer` owns the indexing config (chunk size, overlap, embed batch) and
the DB connection, so the pipeline stages don't thread those through every call.
Pipeline per document: read pages -> strip boilerplate -> chunk -> batch-embed
-> store. Chunks are made per page (exact page numbers for citations) and a
re-index replaces a document's rows (delete-by-source), so runs are idempotent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pypdf import PdfReader

from payments_rag.adapters import db
from payments_rag.indexing.chunker import chunk_text
from payments_rag.adapters.embedding import embed
from payments_rag.indexing.textprep import clean_page, find_repeated_lines

logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    source: str
    pages: int
    pages_with_text: int
    chunks: int


class CorpusIndexer:
    """Indexes corpus PDFs into pgvector."""

    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        chunk_size: int = 300,
        overlap: int = 50,
        embed_batch: int = 100,
    ) -> None:
        self.conn = conn
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.embed_batch = embed_batch

    # ----- public API -----

    def index_corpus(self, corpus_dir: str | Path = "corpus/raw") -> list[IndexStats]:
        """Index every PDF in a directory."""
        pdfs = sorted(Path(corpus_dir).glob("*.pdf"))
        if not pdfs:
            raise SystemExit(f"no corpus PDFs found in {corpus_dir}")
        return [self.index_pdf(p) for p in pdfs]

    def index_pdf(self, path: str | Path) -> IndexStats:
        """Index a single PDF. Replaces any existing rows for it."""
        path = Path(path)
        pages = self._read_pages(path)
        boilerplate = find_repeated_lines(pages)

        records: list[tuple[int, str]] = []
        pages_with_text = 0
        for page_no, raw in enumerate(pages, start=1):
            text = clean_page(raw, boilerplate)
            if not text:
                continue  # blank / image-only / boilerplate-only page
            pages_with_text += 1
            for chunk in chunk_text(text, size=self.chunk_size, overlap=self.overlap):
                records.append((page_no, chunk))

        db.delete_source(self.conn, path.name)  # idempotent reindex
        self._embed_and_store(path.name, records)
        self.conn.commit()

        stats = IndexStats(path.name, len(pages), pages_with_text, len(records))
        logger.info(
            "indexed %s: %d pages (%d with text) -> %d chunks",
            stats.source,
            stats.pages,
            stats.pages_with_text,
            stats.chunks,
        )
        return stats

    # ----- internals -----

    @staticmethod
    def _read_pages(path: Path) -> list[str]:
        return [page.extract_text() or "" for page in PdfReader(str(path)).pages]

    def _embed_and_store(self, source: str, records: list[tuple[int, str]]) -> None:
        """Embed chunks in batches and insert each with its page + order."""
        for start in range(0, len(records), self.embed_batch):
            batch = records[start : start + self.embed_batch]
            vectors = embed([text for _, text in batch])
            for offset, ((page_no, text), vec) in enumerate(zip(batch, vectors)):
                db.insert_chunk(
                    self.conn,
                    source=source,
                    page=page_no,
                    chunk_index=start + offset,
                    text=text,
                    embedding=vec,
                )
            logger.info(
                "  %s: embedded %d/%d chunks",
                source,
                min(start + self.embed_batch, len(records)),
                len(records),
            )
