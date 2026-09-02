"""Corpus indexer: PDF files -> chunks -> embeddings -> pgvector.

`CorpusIndexer` owns the indexing config (chunk size, overlap, embed batch) and
the DB connection, so the pipeline stages don't thread those through every call.
Pipeline per document: read pages (adapters.pdf) -> strip boilerplate -> chunk
-> batch-embed -> store. Chunks are made per page (exact page numbers for
citations) and a re-index replaces a document's rows (delete-by-source), so
runs are idempotent.

With `contextual=True` (ADR-0023) each chunk is embedded with an LLM-written
context blurb prepended, but the STORED text stays the verbatim chunk: cited
evidence must be real spec text (ADR-0006), so the blurb exists only at embed
time.
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from payments_rag.adapters import db, pdf
from payments_rag.adapters.embedding import embed
from payments_rag.domain import IndexStats
from payments_rag.indexing.chunker import chunk_text
from payments_rag.indexing.textprep import clean_page, find_repeated_lines

logger = logging.getLogger(__name__)


class CorpusIndexer:
    """Runs the indexing pipeline over corpus PDFs into pgvector."""

    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        chunk_size: int = 300,
        overlap: int = 50,
        embed_batch: int = 100,
        contextual: bool = False,
    ) -> None:
        self.conn = conn
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.embed_batch = embed_batch
        self.contextual = contextual

    def index_corpus(self, corpus_dir: str | Path = "corpus/raw") -> list[IndexStats]:
        """Index every PDF in a directory."""
        pdfs = sorted(Path(corpus_dir).glob("*.pdf"))
        if not pdfs:
            raise SystemExit(f"no corpus PDFs found in {corpus_dir}")
        return [self.index_pdf(p) for p in pdfs]

    def index_pdf(self, path: str | Path) -> IndexStats:
        """Index a single PDF. Replaces any existing rows for it."""
        path = Path(path)
        pages = pdf.read_pages(path)
        boilerplate = find_repeated_lines(pages)

        cleaned: list[tuple[int, str]] = []  # (page_no, cleaned page text)
        pages_with_text = 0
        for page_no, raw in enumerate(pages, start=1):
            text = clean_page(raw, boilerplate)
            if not text:
                continue  # blank / image-only / boilerplate-only page
            pages_with_text += 1
            cleaned.append((page_no, text))

        # records: (page_no, stored_text, embed_text) - identical unless contextual
        records: list[tuple[int, str, str]] = []
        doc_summary = self._summarize(path.name, cleaned) if self.contextual else ""
        for page_no, text in cleaned:
            chunks = chunk_text(text, size=self.chunk_size, overlap=self.overlap)
            embed_texts = (
                self._contextualize(path.name, doc_summary, page_no, text, chunks)
                if self.contextual
                else chunks
            )
            records += [(page_no, c, e) for c, e in zip(chunks, embed_texts)]

        db.delete_source(self.conn, path.name)  # idempotent reindex
        self._embed_and_store(path.name, records)
        self.conn.commit()

        stats = IndexStats(path.name, len(pages), pages_with_text, len(records))
        logger.info(
            "indexed %s%s: %d pages (%d with text) -> %d chunks",
            stats.source,
            " [contextual]" if self.contextual else "",
            stats.pages,
            stats.pages_with_text,
            stats.chunks,
        )
        return stats

    @staticmethod
    def _summarize(source: str, cleaned: list[tuple[int, str]]) -> str:
        from payments_rag.adapters import contextualizer

        doc_text = "\n".join(text for _, text in cleaned)
        summary = contextualizer.summarize_document(source, doc_text)
        logger.info("%s: document summary for contextual embedding: %.120s...", source, summary)
        return summary

    @staticmethod
    def _contextualize(
        source: str, doc_summary: str, page_no: int, page_text: str, chunks: list[str]
    ) -> list[str]:
        """Blurb-prefixed embed texts; falls back to the bare chunks on failure."""
        from payments_rag.adapters import contextualizer

        try:
            blurbs = contextualizer.contextualize_chunks(
                source, doc_summary, page_no, page_text, chunks
            )
        except Exception as exc:
            logger.warning("%s p%d: contextualization failed, embedding bare chunks: %s",
                           source, page_no, exc)
            return chunks
        return [f"{blurb}\n\n{chunk}" for blurb, chunk in zip(blurbs, chunks)]

    def _embed_and_store(self, source: str, records: list[tuple[int, str, str]]) -> None:
        """Embed chunks in batches and insert each with its page + order."""
        for start in range(0, len(records), self.embed_batch):
            batch = records[start : start + self.embed_batch]
            vectors = embed([embed_text for _, _, embed_text in batch])
            for offset, ((page_no, text, _), vec) in enumerate(zip(batch, vectors)):
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
